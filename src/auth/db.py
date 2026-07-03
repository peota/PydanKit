"""SQLite-backed auth store: users, tokens, login-attempt throttle (ADR 0001).

Async via aiosqlite. One database file (``config.database_path``) holds auth data
and — when ``memory_storage_type="sqlite"`` — conversation history too. Tables are
created on demand with ``CREATE TABLE IF NOT EXISTS`` (ADR 0001: no migrations).

A connection is opened per operation. At SQLite's scale that's cheap, avoids
cross-task connection sharing, and WAL mode keeps readers from blocking a writer.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Literal

import aiosqlite

from src.auth.passwords import hash_password, verify_password
from src.auth.tokens import generate_token, hash_token

TokenKind = Literal["session", "api_key"]

# Sentinel stored as a service account's password_hash. It is not a valid bcrypt
# hash, so verify_password always fails for it — service accounts can hold API keys
# but can never log in with a password (ADR 0002).
SERVICE_PASSWORD_SENTINEL = "!"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    disabled      INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL CHECK (kind IN ('session', 'api_key')),
    name       TEXT,
    created_at REAL NOT NULL,
    expires_at REAL,
    revoked    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS login_attempts (
    identifier TEXT NOT NULL,
    at         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(identifier, at);
"""


@dataclass(frozen=True)
class User:
    """A row from the users table (never carries the password hash outward)."""

    id: int
    username: str
    is_admin: bool
    disabled: bool
    created_at: float
    # True for a passwordless service account (ADR 0002) — holds API keys, can't log in.
    is_service: bool = False


def _to_user(row: aiosqlite.Row) -> User:
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


class AuthStore:
    """Async access layer for the auth tables. Construct with a DB path."""

    def __init__(self, path: str) -> None:
        self._path = path
        # Create tables once, synchronously, so the store is ready to use as soon
        # as it's constructed (no separate async startup step required).
        with sqlite3.connect(self._path) as db:
            db.executescript(_SCHEMA)

    async def _connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self._path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        return db

    async def init(self) -> None:
        """Create tables/indexes if they don't exist. Safe to call repeatedly."""
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    # ---- users ---------------------------------------------------------------

    async def create_user(self, username: str, password: str, *, is_admin: bool = False) -> User:
        """Insert a user with a bcrypt-hashed password. Raises UsernameTakenError."""
        now = time.time()
        db = await self._connect()
        try:
            cursor = await db.execute(
                "INSERT INTO users (username, password_hash, is_admin, disabled, created_at) "
                "VALUES (?, ?, ?, 0, ?)",
                (username, hash_password(password), int(is_admin), now),
            )
            await db.commit()
            user_id = cursor.lastrowid
        except aiosqlite.IntegrityError as exc:
            raise UsernameTakenError(username) from exc
        finally:
            await db.close()
        return User(
            id=user_id, username=username, is_admin=is_admin, disabled=False, created_at=now
        )

    async def create_service_account(self, username: str) -> User:
        """Create a passwordless, non-admin service account (ADR 0002).

        Holds API keys but can never log in (sentinel password hash). Raises
        UsernameTakenError on a duplicate username.
        """
        now = time.time()
        db = await self._connect()
        try:
            cursor = await db.execute(
                "INSERT INTO users (username, password_hash, is_admin, disabled, created_at) "
                "VALUES (?, ?, 0, 0, ?)",
                (username, SERVICE_PASSWORD_SENTINEL, now),
            )
            await db.commit()
            user_id = cursor.lastrowid
        except aiosqlite.IntegrityError as exc:
            raise UsernameTakenError(username) from exc
        finally:
            await db.close()
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
        db = await self._connect()
        try:
            async with db.execute(
                "SELECT 1 FROM users WHERE is_admin = 1 AND disabled = 0 LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        return row is not None

    async def get_user_by_username(self, username: str) -> User | None:
        db = await self._connect()
        try:
            async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        return _to_user(row) if row else None

    async def get_user_by_id(self, user_id: int) -> User | None:
        db = await self._connect()
        try:
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        return _to_user(row) if row else None

    async def list_users(self) -> list[User]:
        db = await self._connect()
        try:
            async with db.execute("SELECT * FROM users ORDER BY id") as cur:
                rows = await cur.fetchall()
        finally:
            await db.close()
        return [_to_user(r) for r in rows]

    async def set_disabled(self, user_id: int, disabled: bool) -> None:
        db = await self._connect()
        try:
            await db.execute("UPDATE users SET disabled = ? WHERE id = ?", (int(disabled), user_id))
            await db.commit()
        finally:
            await db.close()

    async def verify_login(self, username: str, password: str) -> User | None:
        """Return the user iff the password matches and the account is enabled."""
        db = await self._connect()
        try:
            async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
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
        db = await self._connect()
        try:
            await db.execute(
                "INSERT INTO tokens (token_hash, user_id, kind, name, created_at, expires_at, "
                "revoked) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (hash_token(token), user_id, kind, name, now, expires_at),
            )
            await db.commit()
        finally:
            await db.close()
        return token

    async def resolve_token(self, token: str) -> User | None:
        """Resolve a plaintext token to its user, or None.

        None if unknown, revoked, expired, or the owning account is disabled.
        """
        digest = hash_token(token)
        db = await self._connect()
        try:
            async with db.execute(
                "SELECT t.expires_at, t.revoked, u.* FROM tokens t "
                "JOIN users u ON u.id = t.user_id WHERE t.token_hash = ?",
                (digest,),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        if row is None or row["revoked"] or row["disabled"]:
            return None
        if row["expires_at"] is not None and row["expires_at"] < time.time():
            return None
        return _to_user(row)

    async def extend_token(self, token: str, ttl_seconds: float) -> None:
        """Push a token's expiry forward (sliding session refresh). No-op if absent."""
        db = await self._connect()
        try:
            await db.execute(
                "UPDATE tokens SET expires_at = ? WHERE token_hash = ? AND revoked = 0",
                (time.time() + ttl_seconds, hash_token(token)),
            )
            await db.commit()
        finally:
            await db.close()

    async def revoke_token(self, token: str) -> None:
        """Revoke a single token by its plaintext value (logout)."""
        db = await self._connect()
        try:
            await db.execute(
                "UPDATE tokens SET revoked = 1 WHERE token_hash = ?", (hash_token(token),)
            )
            await db.commit()
        finally:
            await db.close()

    async def list_tokens(
        self, user_id: int, *, kind: TokenKind | None = None, include_revoked: bool = False
    ) -> list[TokenInfo]:
        """List a user's tokens as metadata (never the plaintext). Newest first."""
        query = (
            "SELECT token_hash, kind, name, created_at, expires_at, revoked "
            "FROM tokens WHERE user_id = ?"
        )
        params: list = [user_id]
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        if not include_revoked:
            query += " AND revoked = 0"
        query += " ORDER BY created_at DESC"
        db = await self._connect()
        try:
            async with db.execute(query, params) as cur:
                rows = await cur.fetchall()
        finally:
            await db.close()
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
        db = await self._connect()
        try:
            cursor = await db.execute(
                "UPDATE tokens SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
                (token_hash,),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    # ---- login throttle ------------------------------------------------------

    async def record_failure(self, identifier: str) -> None:
        """Record one failed login for an identifier (e.g. username or client IP)."""
        db = await self._connect()
        try:
            await db.execute(
                "INSERT INTO login_attempts (identifier, at) VALUES (?, ?)",
                (identifier, time.time()),
            )
            await db.commit()
        finally:
            await db.close()

    async def is_locked_out(
        self, identifier: str, max_attempts: int, window_seconds: float
    ) -> bool:
        """True if failures within the window meet/exceed max_attempts."""
        cutoff = time.time() - window_seconds
        db = await self._connect()
        try:
            async with db.execute(
                "SELECT COUNT(*) AS n FROM login_attempts WHERE identifier = ? AND at >= ?",
                (identifier, cutoff),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        return row["n"] >= max_attempts

    async def clear_failures(self, identifier: str) -> None:
        """Drop recorded failures for an identifier after a successful login."""
        db = await self._connect()
        try:
            await db.execute("DELETE FROM login_attempts WHERE identifier = ?", (identifier,))
            await db.commit()
        finally:
            await db.close()
