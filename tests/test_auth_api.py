"""Integration tests for auth-enabled API behavior (ADR 0001, Phase 3).

Boots the app with AUTH_ENABLED=true against a temp SQLite DB and proves the
contract: unauthenticated calls are rejected, and an authenticated user can only
reach their own data. Offline — no model is invoked (we never hit /chat's happy
path, only the auth checks that run before it).
"""

import asyncio
import importlib

import pytest

pytest.importorskip("fastapi")

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart


def _turn(prompt: str, reply: str) -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content=prompt)]),
        ModelResponse(parts=[TextPart(content=reply)]),
    ]


def _clear_caches() -> None:
    from src.auth.dependencies import get_auth_store
    from src.config import get_settings
    from src.db import get_engine
    from src.memory.manager import get_memory_manager

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_auth_store.cache_clear()
    get_memory_manager.cache_clear()


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """App booted with auth on, a temp DB, and alice/bob seeded with one session each."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    db_url = f"sqlite+aiosqlite:///{str(tmp_path / 'app.db').replace(chr(92), '/')}"
    monkeypatch.setenv("DATABASE_URL", db_url)  # overrides any real .env DATABASE_URL
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "2")  # keep the lockout test fast
    _clear_caches()

    import src.api as api

    importlib.reload(api)

    # Seed two users and one conversation each (via the same singletons the app uses).
    from src.memory.manager import get_memory_manager

    store = api.get_auth_store()
    asyncio.run(store.create_user("alice", "pw-alice"))
    asyncio.run(store.create_user("bob", "pw-bob"))
    mm = get_memory_manager()
    asyncio.run(mm.save_turn(session_id=None, new_messages=_turn("hi", "yo"), user_id="alice"))
    asyncio.run(mm.save_turn(session_id=None, new_messages=_turn("hi", "yo"), user_id="bob"))

    from fastapi.testclient import TestClient

    yield api, TestClient(api.app)

    # Restore env + module so auth-off tests aren't polluted.
    monkeypatch.undo()
    _clear_caches()
    importlib.reload(api)


def _login(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


# ---- gate ---------------------------------------------------------------------


def test_unauthenticated_calls_rejected(auth_client):
    _, client = auth_client
    assert client.get("/sessions").status_code == 401
    assert client.get("/info").status_code == 401
    assert client.get("/memory/stats").status_code == 401
    assert client.post("/chat", json={"prompt": "hi"}).status_code == 401
    # /health stays public.
    assert client.get("/health").status_code == 200


def test_bad_password_then_lockout(auth_client):
    _, client = auth_client
    assert _login(client, "alice", "wrong").status_code == 401
    assert _login(client, "alice", "wrong").status_code == 401
    # LOGIN_MAX_ATTEMPTS=2 reached -> locked out (even a correct password is refused).
    assert _login(client, "alice", "pw-alice").status_code == 429


# ---- isolation (the whole point of world B) -----------------------------------


def test_login_scopes_sessions_to_caller(auth_client):
    _, client = auth_client
    assert _login(client, "alice", "pw-alice").status_code == 200
    r = client.get("/sessions")
    assert r.status_code == 200
    assert [s["session_id"] for s in r.json()["sessions"]] == ["user:alice"]


def test_cannot_read_or_delete_another_users_session(auth_client):
    _, client = auth_client
    _login(client, "alice", "pw-alice")
    # Alice reaches her own session...
    assert client.get("/sessions/user:alice").status_code == 200
    # ...but Bob's is a 404 (existence not leaked), and she can't delete it.
    # (DELETE is a cookie-authed unsafe method, so it needs the CSRF header to get
    # past the resolver and reach the ownership check.)
    assert client.get("/sessions/user:bob").status_code == 404
    csrf = {"X-Requested-With": "fetch"}
    assert client.delete("/sessions/user:bob", headers=csrf).status_code == 404
    # Bob's data is still intact after Alice's probe.
    _login(client, "bob", "pw-bob")
    assert client.get("/sessions/user:bob").status_code == 200


def test_memory_stats_scoped_to_caller(auth_client):
    _, client = auth_client
    _login(client, "alice", "pw-alice")
    stats = client.get("/memory/stats").json()
    assert stats["total_sessions"] == 1  # only alice's, not bob's


def test_deps_namespace_authenticated_sessions():
    """_deps_for scopes every authed thread under user:<name>; anon uses the raw id."""
    from src.api import ChatRequest, _deps_for
    from src.auth.db import User

    alice = User(id=1, username="alice", is_admin=False, disabled=False, created_at=0.0)
    assert _deps_for(alice, ChatRequest(prompt="x")).session_id == "user:alice"
    named = _deps_for(alice, ChatRequest(prompt="x", session_id="work"))
    assert named.session_id == "user:alice:work"
    assert _deps_for(None, ChatRequest(prompt="x", session_id="raw")).session_id == "raw"


def test_named_sessions_listed_scoped_and_isolated(auth_client):
    _, client = auth_client
    # Seed alice two named threads + bob one, directly via the manager (the stored form).
    from src.memory.manager import get_memory_manager

    mm = get_memory_manager()
    asyncio.run(mm.save_turn("user:alice:work", _turn("q", "a"), user_id="alice"))
    asyncio.run(mm.save_turn("user:alice:home", _turn("q", "a"), user_id="alice"))
    asyncio.run(mm.save_turn("user:bob:work", _turn("q", "a"), user_id="bob"))

    _login(client, "alice", "pw-alice")
    ids = {s["session_id"] for s in client.get("/sessions").json()["sessions"]}
    assert {"user:alice:work", "user:alice:home"} <= ids
    assert all(sid.startswith("user:alice") for sid in ids)  # never bob's

    # Alice reads her own thread's messages...
    r = client.get("/sessions/user:alice:work/messages")
    assert r.status_code == 200
    assert [m["role"] for m in r.json()["messages"]] == ["user", "assistant"]
    # ...but bob's thread is 404 (existence not leaked), even though it exists.
    assert client.get("/sessions/user:bob:work/messages").status_code == 404


# ---- transports ---------------------------------------------------------------


def test_api_key_header_path(auth_client):
    api, client = auth_client
    bob = asyncio.run(api.get_auth_store().get_user_by_username("bob"))
    key = asyncio.run(api.get_auth_store().issue_token(bob.id, "api_key", name="ci"))
    r = client.get("/sessions", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200
    assert [s["session_id"] for s in r.json()["sessions"]] == ["user:bob"]


def test_invalid_token_rejected(auth_client):
    _, client = auth_client
    r = client.get("/sessions", headers={"X-API-Key": "not-a-real-token"})
    assert r.status_code == 401


def test_cookie_post_requires_csrf_header(auth_client):
    _, client = auth_client
    _login(client, "alice", "pw-alice")
    # Cookie present + unsafe method + no X-Requested-With -> blocked before the model runs.
    assert client.post("/chat", json={"prompt": "hi"}).status_code == 403


def test_logout_revokes_session(auth_client):
    _, client = auth_client
    _login(client, "alice", "pw-alice")
    assert client.get("/sessions").status_code == 200
    # Logout needs the CSRF header (cookie-authenticated POST).
    assert client.post("/auth/logout", headers={"X-Requested-With": "fetch"}).status_code == 200
    assert client.get("/sessions").status_code == 401


# ---- admin panel (ADR 0002) ---------------------------------------------------

CSRF = {"X-Requested-With": "fetch"}


@pytest.fixture
def admin_client(auth_client):
    """auth_client plus an admin ('root') and a non-admin already seeded."""
    api, client = auth_client
    asyncio.run(api.get_auth_store().create_user("root", "pw-root", is_admin=True))
    return api, client


def test_non_admin_cannot_reach_admin_routes(admin_client):
    _, client = admin_client
    _login(client, "alice", "pw-alice")  # alice is a normal user
    assert client.get("/admin/users").status_code == 403
    assert client.post("/admin/users", json={"username": "svc"}, headers=CSRF).status_code == 403


def test_unauthenticated_admin_routes_401(admin_client):
    _, client = admin_client
    assert client.get("/admin/users").status_code == 401


def test_admin_create_service_account_and_issue_key(admin_client):
    api, client = admin_client
    _login(client, "root", "pw-root")

    # Create a service account.
    r = client.post("/admin/users", json={"username": "ci-bot"}, headers=CSRF)
    assert r.status_code == 201
    acct = r.json()
    assert acct["is_service"] and not acct["is_admin"]
    uid = acct["id"]

    # Issue a key — plaintext returned once.
    r = client.post(f"/admin/users/{uid}/keys", json={"name": "ci"}, headers=CSRF)
    assert r.status_code == 201
    key = r.json()["key"]
    key_hash = r.json()["token_hash"]

    # Test the key on a cookie-less client (the admin `client` has a session cookie,
    # which the resolver prefers over the Authorization header).
    from fastapi.testclient import TestClient

    bare = TestClient(api.app)
    assert bare.get("/sessions", headers={"Authorization": f"Bearer {key}"}).status_code == 200

    # It appears in the list (metadata only, no plaintext).
    r = client.get(f"/admin/users/{uid}/keys")
    assert [k["name"] for k in r.json()] == ["ci"]
    assert "key" not in r.json()[0]

    # Revoke it -> gone from the list and no longer authenticates.
    assert client.delete(f"/admin/keys/{key_hash}", headers=CSRF).status_code == 200
    assert client.get(f"/admin/users/{uid}/keys").json() == []
    assert bare.get("/sessions", headers={"Authorization": f"Bearer {key}"}).status_code == 401


def test_admin_cannot_grant_admin_or_disable_admins(admin_client):
    api, client = admin_client
    _login(client, "root", "pw-root")
    # Created accounts are never admin.
    acct = client.post("/admin/users", json={"username": "svc2"}, headers=CSRF).json()
    assert acct["is_admin"] is False
    # Admin accounts can't be disabled via the UI (no self/peer lockout).
    root = next(u for u in client.get("/admin/users").json() if u["username"] == "root")
    assert client.post(f"/admin/users/{root['id']}/disable", headers=CSRF).status_code == 400


def test_revoke_unknown_key_404(admin_client):
    _, client = admin_client
    _login(client, "root", "pw-root")
    assert client.delete("/admin/keys/deadbeef", headers=CSRF).status_code == 404


def test_disable_freezes_keys_then_enable_restores(admin_client):
    """Disabling an account makes its keys inert (not revoked); enabling restores them."""
    api, client = admin_client
    _login(client, "root", "pw-root")
    uid = client.post("/admin/users", json={"username": "frost"}, headers=CSRF).json()["id"]
    key = client.post(f"/admin/users/{uid}/keys", json={}, headers=CSRF).json()["key"]

    from fastapi.testclient import TestClient

    bare = TestClient(api.app)
    auth = {"Authorization": f"Bearer {key}"}
    assert bare.get("/sessions", headers=auth).status_code == 200

    # Disable -> key stops working, but it's still listed (frozen, not revoked).
    assert client.post(f"/admin/users/{uid}/disable", headers=CSRF).status_code == 200
    assert bare.get("/sessions", headers=auth).status_code == 401
    assert len(client.get(f"/admin/users/{uid}/keys").json()) == 1

    # Enable -> the same key authenticates again.
    assert client.post(f"/admin/users/{uid}/enable", headers=CSRF).status_code == 200
    assert bare.get("/sessions", headers=auth).status_code == 200


def test_cannot_enable_admin_from_ui(admin_client):
    _, client = admin_client
    _login(client, "root", "pw-root")
    root = next(u for u in client.get("/admin/users").json() if u["username"] == "root")
    assert client.post(f"/admin/users/{root['id']}/enable", headers=CSRF).status_code == 400


def test_cannot_issue_key_for_admin(admin_client):
    """Admin accounts can't be issued API keys (no non-expiring admin credential)."""
    _, client = admin_client
    _login(client, "root", "pw-root")
    root = next(u for u in client.get("/admin/users").json() if u["username"] == "root")
    assert client.post(f"/admin/users/{root['id']}/keys", json={}, headers=CSRF).status_code == 400


def test_admin_routes_404_when_auth_disabled(tmp_path, monkeypatch):
    """With auth off there is no admin identity, so /admin/* is unavailable (404)."""
    monkeypatch.setenv("AUTH_ENABLED", "false")
    _clear_caches()
    import importlib

    import src.api as api

    importlib.reload(api)
    from fastapi.testclient import TestClient

    client = TestClient(api.app)
    try:
        assert client.get("/admin/users").status_code == 404
    finally:
        monkeypatch.undo()
        _clear_caches()
        importlib.reload(api)


def test_wildcard_cors_refused_at_startup(monkeypatch):
    """CORS_ORIGINS=['*'] must fail fast — credentials are on, so a wildcard leaks the cookie."""
    monkeypatch.setenv("CORS_ORIGINS", '["*"]')
    _clear_caches()
    import importlib

    import src.api as api

    try:
        with pytest.raises(ValueError, match="CORS_ORIGINS"):
            importlib.reload(api)
    finally:
        monkeypatch.undo()
        _clear_caches()
        importlib.reload(api)


def test_env_seed_creates_first_admin(tmp_path, monkeypatch):
    """Lifespan seeds an admin from ADMIN_USERNAME/PASSWORD when none exists."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    db_url = f"sqlite+aiosqlite:///{str(tmp_path / 'seed.db').replace(chr(92), '/')}"
    monkeypatch.setenv("DATABASE_URL", db_url)  # overrides any real .env DATABASE_URL
    monkeypatch.setenv("ADMIN_USERNAME", "seeded")
    monkeypatch.setenv("ADMIN_PASSWORD", "seed-pw")
    _clear_caches()
    import importlib

    import src.api as api

    importlib.reload(api)
    from fastapi.testclient import TestClient

    try:
        with TestClient(api.app) as client:  # `with` runs the lifespan (the seed)
            r = client.post("/auth/login", json={"username": "seeded", "password": "seed-pw"})
            assert r.status_code == 200
            assert r.json()["is_admin"] is True
    finally:
        monkeypatch.undo()
        _clear_caches()
        importlib.reload(api)
