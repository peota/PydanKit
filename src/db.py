"""Shared SQLAlchemy Core schema + async engine for auth and memory.

A single async engine, selected by ``DATABASE_URL``, backs both the default SQLite
(zero-config, file-based — light/local use) and PostgreSQL
(``postgresql+asyncpg://…`` — cloud / multi-instance). Tables are defined once here
and created on demand via :func:`ensure_schema` — no migrations;
evolve with Alembic when a real deployment needs schema changes.

Boolean-ish columns are stored as ``Integer`` (0/1) so the same ``= 1`` comparisons
work identically on SQLite and Postgres. Timestamps follow the existing stores:
epoch ``Float`` for auth, ISO ``String`` for memory.
"""

from __future__ import annotations

import asyncio
import weakref
from functools import lru_cache

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    event,
    make_url,
)
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(255), unique=True, nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("is_admin", Integer, nullable=False, default=0),
    Column("disabled", Integer, nullable=False, default=0),
    Column("created_at", Float, nullable=False),
)

tokens = Table(
    "tokens",
    metadata,
    Column("token_hash", String(255), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("name", String(255)),
    Column("created_at", Float, nullable=False),
    Column("expires_at", Float),
    Column("revoked", Integer, nullable=False, default=0),
    CheckConstraint("kind IN ('session', 'api_key')", name="ck_tokens_kind"),
    Index("idx_tokens_user", "user_id"),
)

login_attempts = Table(
    "login_attempts",
    metadata,
    Column("identifier", String(255), nullable=False),
    Column("at", Float, nullable=False),
    Index("idx_login_attempts", "identifier", "at"),
)

memory_sessions = Table(
    "memory_sessions",
    metadata,
    Column("session_id", String(255), primary_key=True),
    Column("user_id", String(255)),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column("message_count", Integer, nullable=False, default=0),
    Column("messages", LargeBinary, nullable=False),
    Index("idx_memory_updated", "updated_at"),
)


def _sqlite_on_connect(dbapi_conn, _record) -> None:
    """Match the old aiosqlite pragmas: WAL for concurrency, enforce foreign keys."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def create_engine_from_url(url: str | URL) -> AsyncEngine:
    """Build an async engine for ``url``, wiring SQLite pragmas and pool.

    Exposed (not just the cached :func:`get_engine`) so tests can point a store at an
    isolated temp database. SQLite uses ``NullPool`` — connections open per operation
    (matching the previous aiosqlite design and avoiding lingering file handles on
    Windows temp DBs). Postgres keeps SQLAlchemy's default async pool.
    """
    url = make_url(url)
    is_sqlite = url.get_backend_name() == "sqlite"
    kwargs: dict = {"future": True}
    if is_sqlite:
        kwargs["poolclass"] = NullPool
    engine = create_async_engine(url, **kwargs)
    if is_sqlite:
        event.listen(engine.sync_engine, "connect", _sqlite_on_connect)
    return engine


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """The process-wide engine, built from ``settings.sqlalchemy_url`` (cached).

    ``lru_cache`` gives us ``get_engine.cache_clear()`` — tests reset it like the
    other singletons (get_settings, get_auth_store, get_memory_manager).
    """
    from src.config import get_settings

    return create_engine_from_url(get_settings().sqlalchemy_url)


_init_lock = asyncio.Lock()
_initialized: weakref.WeakSet = weakref.WeakSet()


async def ensure_schema(engine: AsyncEngine) -> None:
    """Create tables/indexes if absent. Idempotent and cheap after the first call.

    Cached per-engine (via a WeakSet, so disposed engines drop out and can't collide
    on a reused id). ``metadata.create_all`` uses ``checkfirst=True`` regardless.
    """
    if engine in _initialized:
        return
    async with _init_lock:
        if engine in _initialized:
            return
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        _initialized.add(engine)
