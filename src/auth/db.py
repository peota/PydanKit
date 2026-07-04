"""SQLAlchemy-Core auth store: users, tokens, login-attempt throttle.

Async access over a single engine chosen by ``DATABASE_URL`` (see ``src/db.py``):
SQLite by default, PostgreSQL for cloud / multi-instance. The same code runs on both
dialects — SQLAlchemy renders the placeholder, ``RETURNING`` and boolean differences.
Tables are created on demand via ``ensure_schema`` (no migrations).
"""

from __future__ import annotations

import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.auth.passwords import hash_password, verify_password
from src.auth.tokens import generate_token, hash_token
from src.db import create_engine_from_url, ensure_schema, login_attempts, tokens, users

TokenKind = Literal["session", "api_key"]

# Sentinel stored as a service account's password_hash. It is not a valid bcrypt
# hash, so verify_password always fails for it — service accounts can hold API keys
# but can never log in with a password.
SERVICE_PASSWORD_SENTINEL = "!"


@dataclass(frozen=True)
class User:
    """A row from the users table (never carries the password hash outward)."""

    id: int
    username: str
    is_admin: bool
    disabled: bool
    created_at: float
    # True for a passwordless service account — holds API keys, can't log in.
    is_service: bool = False


def _to_user(row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        is_admin=bool(row["is_admin"]),
        disabled=bool(row["disabled"]),
        created_at=row["created_at"],
        is_service=row["password_hash"] == SERVICE_PASSWORD_SENTINEL,
    )


@dataclass(frozen=True)
class TokenInfo:
    """Metadata for a stored token. Never carries the token's plaintext value."""

    token_hash: str  # safe handle: a hash, not the secret; can't authenticate with it
    kind: str
    name: str | None
    created_at: float
    expires_at: float | None
    revoked: bool


class UsernameTakenError(ValueError):
    """Raised when creating a user whose username already exists."""


class InvalidUsernameError(ValueError):
    """Raised when a username uses characters outside the allowed set."""


_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_username(username: str) -> None:
    """Usernames must be non-empty and colon-free (safe charset) so a session id
    ``user:<name>:<thread>`` parses unambiguously back to its owner."""
    if not _USERNAME_RE.fullmatch(username):
        raise InvalidUsernameError(
            f"Invalid username {username!r}: use letters, digits, '_', '.', or '-'."
        )


class AuthStore:
    """Async access layer for the auth tables over a shared SQLAlchemy engine.

    Accepts an ``AsyncEngine`` (production passes the shared ``get_engine()``), or a
    URL / bare file path (tests, CLI convenience) from which a SQLite engine is built.
    """

    def __init__(self, engine_or_url: AsyncEngine | str) -> None:
        if isinstance(engine_or_url, AsyncEngine):
            self._engine = engine_or_url
        elif "://" in engine_or_url:
            self._engine = create_engine_from_url(engine_or_url)
        else:
            # Bare filesystem path -> SQLite URL (forward slashes for Windows safety).
            path = engine_or_url.replace("\\", "/")
            self._engine = create_engine_from_url(f"sqlite+aiosqlite:///{path}")

    @asynccontextmanager
    async def _begin(self):
        """A committing transaction, with the schema ensured first."""
        await ensure_schema(self._engine)
        async with self._engine.begin() as conn:
            yield conn

    @asynccontextmanager
    async def _connect(self):
        """A read-only connection, with the schema ensured first."""
        await ensure_schema(self._engine)
        async with self._engine.connect() as conn:
            yield conn

    async def init(self) -> None:
        """Create tables/indexes if they don't exist. Safe to call repeatedly."""
        await ensure_schema(self._engine)

    # ---- users ---------------------------------------------------------------

    async def create_user(self, username: str, password: str, *, is_admin: bool = False) -> User:
        """Insert a user with a bcrypt-hashed password. Raises UsernameTakenError."""
        _validate_username(username)
        now = time.time()
        try:
            async with self._begin() as conn:
                result = await conn.execute(
                    insert(users).values(
                        username=username,
                        password_hash=hash_password(password),
                        is_admin=int(is_admin),
                        disabled=0,
                        created_at=now,
                    )
                )
                user_id = result.inserted_primary_key[0]
        except IntegrityError as exc:
            raise UsernameTakenError(username) from exc
        return User(
            id=user_id, username=username, is_admin=is_admin, disabled=False, created_at=now
        )

    async def create_service_account(self, username: str) -> User:
        """Create a passwordless, non-admin service account.

        Holds API keys but can never log in (sentinel password hash). Raises
        UsernameTakenError on a duplicate username.
        """
        _validate_username(username)
        now = time.time()
        try:
            async with self._begin() as conn:
                result = await conn.execute(
                    insert(users).values(
                        username=username,
                        password_hash=SERVICE_PASSWORD_SENTINEL,
                        is_admin=0,
                        disabled=0,
                        created_at=now,
                    )
                )
                user_id = result.inserted_primary_key[0]
        except IntegrityError as exc:
            raise UsernameTakenError(username) from exc
        return User(
            id=user_id,
            username=username,
            is_admin=False,
            disabled=False,
            created_at=now,
            is_service=True,
        )

    async def has_admin(self) -> bool:
        """True if at least one enabled admin exists (used to gate env-seeding)."""
        async with self._connect() as conn:
            result = await conn.execute(
                select(users.c.id).where(users.c.is_admin == 1, users.c.disabled == 0).limit(1)
            )
            return result.first() is not None

    async def get_user_by_username(self, username: str) -> User | None:
        async with self._connect() as conn:
            result = await conn.execute(select(users).where(users.c.username == username))
            row = result.mappings().first()
        return _to_user(row) if row else None

    async def get_user_by_id(self, user_id: int) -> User | None:
        async with self._connect() as conn:
            result = await conn.execute(select(users).where(users.c.id == user_id))
            row = result.mappings().first()
        return _to_user(row) if row else None

    async def list_users(self) -> list[User]:
        async with self._connect() as conn:
            result = await conn.execute(select(users).order_by(users.c.id))
            rows = result.mappings().all()
        return [_to_user(r) for r in rows]

    async def set_disabled(self, user_id: int, disabled: bool) -> None:
        async with self._begin() as conn:
            await conn.execute(
                update(users).where(users.c.id == user_id).values(disabled=int(disabled))
            )

    async def verify_login(self, username: str, password: str) -> User | None:
        """Return the user iff the password matches and the account is enabled."""
        async with self._connect() as conn:
            result = await conn.execute(select(users).where(users.c.username == username))
            row = result.mappings().first()
        if row is None or row["disabled"]:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return _to_user(row)

    # ---- tokens --------------------------------------------------------------

    async def issue_token(
        self,
        user_id: int,
        kind: TokenKind,
        *,
        name: str | None = None,
        ttl_seconds: float | None = None,
    ) -> str:
        """Mint an opaque token, store only its hash, and return the plaintext.

        The plaintext is shown to the caller exactly once; only the hash is kept.
        ``ttl_seconds=None`` means no expiry (typical for API keys).
        """
        token = generate_token()
        now = time.time()
        expires_at = now + ttl_seconds if ttl_seconds is not None else None
        async with self._begin() as conn:
            await conn.execute(
                insert(tokens).values(
                    token_hash=hash_token(token),
                    user_id=user_id,
                    kind=kind,
                    name=name,
                    created_at=now,
                    expires_at=expires_at,
                    revoked=0,
                )
            )
        return token

    async def resolve_token(self, token: str) -> User | None:
        """Resolve a plaintext token to its user, or None.

        None if unknown, revoked, expired, or the owning account is disabled.
        """
        digest = hash_token(token)
        joined = tokens.join(users, users.c.id == tokens.c.user_id)
        query = (
            select(
                tokens.c.expires_at,
                tokens.c.revoked,
                users.c.id,
                users.c.username,
                users.c.is_admin,
                users.c.disabled,
                users.c.created_at,
                users.c.password_hash,
            )
            .select_from(joined)
            .where(tokens.c.token_hash == digest)
        )
        async with self._connect() as conn:
            result = await conn.execute(query)
            row = result.mappings().first()
        if row is None or row["revoked"] or row["disabled"]:
            return None
        if row["expires_at"] is not None and row["expires_at"] < time.time():
            return None
        return _to_user(row)

    async def extend_token(self, token: str, ttl_seconds: float) -> None:
        """Push a token's expiry forward (sliding session refresh). No-op if absent."""
        async with self._begin() as conn:
            await conn.execute(
                update(tokens)
                .where(tokens.c.token_hash == hash_token(token), tokens.c.revoked == 0)
                .values(expires_at=time.time() + ttl_seconds)
            )

    async def revoke_token(self, token: str) -> None:
        """Revoke a single token by its plaintext value (logout)."""
        async with self._begin() as conn:
            await conn.execute(
                update(tokens).where(tokens.c.token_hash == hash_token(token)).values(revoked=1)
            )

    async def list_tokens(
        self, user_id: int, *, kind: TokenKind | None = None, include_revoked: bool = False
    ) -> list[TokenInfo]:
        """List a user's tokens as metadata (never the plaintext). Newest first."""
        query = select(
            tokens.c.token_hash,
            tokens.c.kind,
            tokens.c.name,
            tokens.c.created_at,
            tokens.c.expires_at,
            tokens.c.revoked,
        ).where(tokens.c.user_id == user_id)
        if kind is not None:
            query = query.where(tokens.c.kind == kind)
        if not include_revoked:
            query = query.where(tokens.c.revoked == 0)
        query = query.order_by(tokens.c.created_at.desc())
        async with self._connect() as conn:
            result = await conn.execute(query)
            rows = result.mappings().all()
        return [
            TokenInfo(
                token_hash=r["token_hash"],
                kind=r["kind"],
                name=r["name"],
                created_at=r["created_at"],
                expires_at=r["expires_at"],
                revoked=bool(r["revoked"]),
            )
            for r in rows
        ]

    async def revoke_token_by_hash(self, token_hash: str) -> bool:
        """Revoke a token by its stored hash (the admin-UI handle). Returns True if a
        row was affected. The hash is not the secret and can't be used to authenticate.
        """
        async with self._begin() as conn:
            result = await conn.execute(
                update(tokens)
                .where(tokens.c.token_hash == token_hash, tokens.c.revoked == 0)
                .values(revoked=1)
            )
            return result.rowcount > 0

    # ---- login throttle ------------------------------------------------------

    async def record_failure(self, identifier: str) -> None:
        """Record one failed login for an identifier (e.g. username or client IP)."""
        async with self._begin() as conn:
            await conn.execute(insert(login_attempts).values(identifier=identifier, at=time.time()))

    async def is_locked_out(
        self, identifier: str, max_attempts: int, window_seconds: float
    ) -> bool:
        """True if failures within the window meet/exceed max_attempts."""
        cutoff = time.time() - window_seconds
        async with self._connect() as conn:
            result = await conn.execute(
                select(func.count())
                .select_from(login_attempts)
                .where(login_attempts.c.identifier == identifier, login_attempts.c.at >= cutoff)
            )
            count = result.scalar_one()
        return count >= max_attempts

    async def clear_failures(self, identifier: str) -> None:
        """Drop recorded failures for an identifier after a successful login."""
        async with self._begin() as conn:
            await conn.execute(
                delete(login_attempts).where(login_attempts.c.identifier == identifier)
            )
