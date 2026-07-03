"""Durable SQLite backend for conversation memory (ADR 0001, Phase 2).

Lives in its own module so ``storage.py`` (which the default in-memory path always
imports) never pulls in ``aiosqlite``. Selected by ``memory_storage_type="sqlite"``
and imported lazily from ``get_memory_manager``. Requires the ``[auth]`` extra.

One session = one row holding the full message list as a JSON blob, serialized with
Pydantic AI's ``ModelMessagesTypeAdapter`` so it round-trips exactly (tool calls and
returns included) and can be replayed via ``message_history``. Blob-per-session
mirrors ``InMemoryStorage`` semantics and is fine at this template's scale.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

import aiosqlite
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from src.memory.models import SessionMetadata
from src.memory.storage import MemoryStorage

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_sessions (
    session_id    TEXT PRIMARY KEY,
    user_id       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    messages      BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_updated ON memory_sessions(updated_at);
"""

# Insert-or-replace for a session. created_at is written only on INSERT; the conflict
# branch never touches it, so an existing row keeps its original created_at with no
# pre-read.
_UPSERT = (
    "INSERT INTO memory_sessions "
    "(session_id, user_id, created_at, updated_at, message_count, messages) "
    "VALUES (?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(session_id) DO UPDATE SET "
    "updated_at=excluded.updated_at, message_count=excluded.message_count, "
    "messages=excluded.messages"
)


def _user_id_from_session(session_id: str) -> str | None:
    """Mirror InMemoryStorage: derive user_id from the 'user:<id>' convention."""
    if session_id.startswith("user:"):
        return session_id.split(":", 1)[1]
    return None


def _to_metadata(row: aiosqlite.Row) -> SessionMetadata:
    return SessionMetadata(
        session_id=row["session_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        message_count=row["message_count"],
        user_id=row["user_id"],
    )


class SqliteMemoryStorage(MemoryStorage):
    """SQLite-backed conversation memory: durable and shared across workers."""

    def __init__(self, path: str) -> None:
        self._path = path
        # Create the table once, synchronously, so async paths can assume it exists.
        with sqlite3.connect(self._path) as db:
            db.executescript(_SCHEMA)
        logger.debug("Initialized SqliteMemoryStorage at %s", path)

    async def get_messages(self, session_id: str, limit: int | None = None) -> list[ModelMessage]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT messages FROM memory_sessions WHERE session_id = ?", (session_id,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return []
        messages = ModelMessagesTypeAdapter.validate_json(row[0])
        if limit is not None and limit > 0:
            messages = messages[-limit:]
        logger.debug("Retrieved %d messages for session %s", len(messages), session_id)
        return messages

    async def save_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        # Full replace (last-writer-wins by design). No pre-read: _UPSERT preserves an
        # existing row's created_at on conflict.
        blob = ModelMessagesTypeAdapter.dump_json(list(messages))
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                _UPSERT,
                (session_id, _user_id_from_session(session_id), now, now, len(messages), blob),
            )
            await db.commit()
        logger.debug("Saved %d messages for session %s", len(messages), session_id)

    async def append_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        # Atomic read-modify-write: BEGIN IMMEDIATE takes the write lock up front so
        # concurrent appenders (multiple workers on the same session) serialize instead
        # of clobbering each other's turns. isolation_level=None => manual transactions.
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self._path, isolation_level=None) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                async with db.execute(
                    "SELECT messages FROM memory_sessions WHERE session_id = ?", (session_id,)
                ) as cur:
                    row = await cur.fetchone()
                existing = ModelMessagesTypeAdapter.validate_json(row[0]) if row else []
                combined = existing + list(messages)
                blob = ModelMessagesTypeAdapter.dump_json(combined)
                await db.execute(
                    _UPSERT,
                    (session_id, _user_id_from_session(session_id), now, now, len(combined), blob),
                )
                await db.execute("COMMIT")
            except Exception:
                await db.execute("ROLLBACK")
                raise
        logger.debug("Appended %d messages to session %s", len(messages), session_id)

    async def clear_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM memory_sessions WHERE session_id = ?", (session_id,))
            await db.commit()
        logger.debug("Cleared session %s", session_id)

    async def list_sessions(self) -> list[SessionMetadata]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT session_id, user_id, created_at, updated_at, message_count "
                "FROM memory_sessions ORDER BY updated_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [_to_metadata(r) for r in rows]

    async def get_metadata(self, session_id: str) -> SessionMetadata | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT session_id, user_id, created_at, updated_at, message_count "
                "FROM memory_sessions WHERE session_id = ?",
                (session_id,),
            ) as cur:
                row = await cur.fetchone()
        return _to_metadata(row) if row else None
