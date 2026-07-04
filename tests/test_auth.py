"""Unit tests for the auth core — offline, no API key.

Requires the ``[auth]`` extra (aiosqlite, bcrypt).
"""

import pytest

from src.auth.db import AuthStore, UsernameTakenError
from src.auth.passwords import hash_password, verify_password
from src.auth.tokens import generate_token, hash_token


@pytest.fixture
async def store(db_engine):
    s = AuthStore(db_engine)
    await s.init()
    return s


# ---- passwords ---------------------------------------------------------------


def test_password_hash_roundtrip():
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"
    assert verify_password("s3cret-pw", h)
    assert not verify_password("wrong", h)


def test_password_over_72_bytes_truncates_consistently():
    base = "a" * 72
    h = hash_password(base)
    # Anything sharing the first 72 bytes verifies (documented bcrypt behavior).
    assert verify_password(base + "EXTRA", h)


def test_verify_against_garbage_hash_is_false_not_error():
    assert not verify_password("x", "not-a-real-hash")


# ---- tokens ------------------------------------------------------------------


def test_tokens_unique_and_hash_is_deterministic():
    a, b = generate_token(), generate_token()
    assert a != b
    assert hash_token(a) == hash_token(a)
    assert hash_token(a) != hash_token(b)


# ---- users -------------------------------------------------------------------


async def test_create_and_fetch_user(store):
    user = await store.create_user("alice", "pw", is_admin=True)
    assert user.username == "alice"
    assert user.is_admin
    fetched = await store.get_user_by_username("alice")
    assert fetched == user
    assert await store.get_user_by_id(user.id) == user


async def test_duplicate_username_raises(store):
    await store.create_user("alice", "pw")
    with pytest.raises(UsernameTakenError):
        await store.create_user("alice", "other")


async def test_invalid_username_rejected(store):
    from src.auth.db import InvalidUsernameError

    # A colon would break the `user:<name>:<thread>` session namespace.
    with pytest.raises(InvalidUsernameError):
        await store.create_user("bad:name", "pw")
    with pytest.raises(InvalidUsernameError):
        await store.create_service_account("has space")


async def test_verify_login(store):
    await store.create_user("bob", "hunter2")
    assert (await store.verify_login("bob", "hunter2")).username == "bob"
    assert await store.verify_login("bob", "wrong") is None
    assert await store.verify_login("nobody", "hunter2") is None


async def test_disabled_user_cannot_log_in(store):
    user = await store.create_user("bob", "pw")
    await store.set_disabled(user.id, True)
    assert await store.verify_login("bob", "pw") is None


# ---- tokens against the store ------------------------------------------------


async def test_issue_resolve_revoke_token(store):
    user = await store.create_user("alice", "pw")
    token = await store.issue_token(user.id, "api_key", name="ci")
    assert (await store.resolve_token(token)).id == user.id

    await store.revoke_token(token)
    assert await store.resolve_token(token) is None


async def test_expired_token_does_not_resolve(store):
    user = await store.create_user("alice", "pw")
    token = await store.issue_token(user.id, "session", ttl_seconds=-1)
    assert await store.resolve_token(token) is None


async def test_extend_token_refreshes_expiry(store):
    user = await store.create_user("alice", "pw")
    token = await store.issue_token(user.id, "session", ttl_seconds=-1)
    assert await store.resolve_token(token) is None  # expired
    await store.extend_token(token, ttl_seconds=3600)
    assert (await store.resolve_token(token)).id == user.id


async def test_token_of_disabled_user_does_not_resolve(store):
    user = await store.create_user("alice", "pw")
    token = await store.issue_token(user.id, "session", ttl_seconds=3600)
    await store.set_disabled(user.id, True)
    assert await store.resolve_token(token) is None


async def test_unknown_token_resolves_to_none(store):
    assert await store.resolve_token("never-issued") is None


# ---- login throttle ----------------------------------------------------------


async def test_service_account_is_passwordless_and_non_admin(store):
    acct = await store.create_service_account("ci-bot")
    assert acct.is_service
    assert not acct.is_admin
    # Reads back as a service account, and can never log in with a password.
    fetched = await store.get_user_by_username("ci-bot")
    assert fetched.is_service
    assert await store.verify_login("ci-bot", "") is None
    assert await store.verify_login("ci-bot", "!") is None


async def test_service_account_can_hold_api_key(store):
    acct = await store.create_service_account("ci-bot")
    token = await store.issue_token(acct.id, "api_key", name="ci")
    assert (await store.resolve_token(token)).id == acct.id


async def test_has_admin(store):
    assert not await store.has_admin()
    await store.create_service_account("svc")  # non-admin doesn't count
    assert not await store.has_admin()
    await store.create_user("root", "pw", is_admin=True)
    assert await store.has_admin()


async def test_list_and_revoke_tokens_by_hash(store):
    user = await store.create_user("alice", "pw")
    t1 = await store.issue_token(user.id, "api_key", name="k1")
    await store.issue_token(user.id, "api_key", name="k2")

    keys = await store.list_tokens(user.id, kind="api_key")
    assert {k.name for k in keys} == {"k1", "k2"}
    assert all(k.token_hash and not k.revoked for k in keys)

    # Revoke k1 by its hash handle; it drops out of the default (active-only) list.
    k1_hash = next(k.token_hash for k in keys if k.name == "k1")
    assert await store.revoke_token_by_hash(k1_hash) is True
    assert await store.resolve_token(t1) is None
    remaining = await store.list_tokens(user.id, kind="api_key")
    assert {k.name for k in remaining} == {"k2"}
    # Revoking an unknown/already-revoked hash is a no-op.
    assert await store.revoke_token_by_hash(k1_hash) is False


async def test_lockout_after_max_attempts(store):
    for _ in range(3):
        assert not await store.is_locked_out("ip:1.2.3.4", max_attempts=3, window_seconds=60)
        await store.record_failure("ip:1.2.3.4")
    assert await store.is_locked_out("ip:1.2.3.4", max_attempts=3, window_seconds=60)

    await store.clear_failures("ip:1.2.3.4")
    assert not await store.is_locked_out("ip:1.2.3.4", max_attempts=3, window_seconds=60)
