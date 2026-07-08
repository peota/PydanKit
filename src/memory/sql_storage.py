"""SQLAlchemy-Core conversation memory: durable, SQLite or Postgres.

Selected by ``memory_storage_type`` in ``("sql", "sqlite")`` and imported lazily from
``get_memory_manager`` so the default in-memory path never needs SQLAlchemy. Runs on
the shared ``DATABASE_URL`` engine (``src/db.py``).

One session = one row holding the full message list as a blob, serialized with
Pydantic AI's ``ModelMessagesTypeAdapter`` so it round-trips exactly (tool calls and
returns included) and replays via ``message_history``.

Concurrency: ``append`` serializes per session with an in-process ``asyncio.Lock``
(covers the SQLite single-instance model) *and* ``SELECT … FOR UPDATE`` on Postgres
(covers multi-instance row locking). ``save`` is intentionally last-writer-wins.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from src.db import create_engine_from_url, ensure_schema, memory_sessions
from src.memory.models import SessionMetadata
from src.memory.storage import MemoryStorage, make_preview

logger = logging.getLogger(__name__)

# The messages blob is included so we can derive a per-session title (first user
# message). Session lists are sidebar-sized, so parsing each blob is cheap enough;
# denormalize a title column (with a migration) if you ever list thousands.
_SESSION_COLUMNS = (
    memory_sessions.c.session_id,
    memory_sessions.c.user_id,
    memory_sessions.c.created_at,
    memory_sessions.c.updated_at,
    memory_sessions.c.message_count,
    memory_sessions.c.messages,
)


def _user_id_from_session(session_id: str) -> str | None:
    """Owner from the session id: user:<owner> or user:<owner>:<thread> -> <owner>."""
    if session_id.startswith("user:"):
        return session_id.split(":")[1]
    return None


def _to_metadata(row) -> SessionMetadata:
    return SessionMetadata(
        session_id=row["session_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        message_count=row["message_count"],
        user_id=row["user_id"],
        preview=make_preview(ModelMessagesTypeAdapter.validate_json(row["messages"])),
    )


class SqlMemoryStorage(MemoryStorage):
    """SQL-backed conversation memory over the shared engine (SQLite or Postgres).

    Accepts an ``AsyncEngine`` (production passes the shared ``get_engine()``), or a
    URL / bare file path (tests) from which a SQLite engine is built.
    """

    def __init__(self, engine_or_url: AsyncEngine | str) -> None:
        if isinstance(engine_or_url, AsyncEngine):
            self._engine = engine_or_url
        elif "://" in engine_or_url:
            self._engine = create_engine_from_url(engine_or_url)
        else:
            path = engine_or_url.replace("\\", "/")
            self._engine = create_engine_from_url(f"sqlite+aiosqlite:///{path}")
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()
        logger.debug("Initialized SqlMemoryStorage on %s", self._engine.url)

    async def _lock_for(self, session_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
            return lock

    async def get_messages(self, session_id: str, limit: int | None = None) -> list[ModelMessage]:
        await ensure_schema(self._engine)
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(memory_sessions.c.messages).where(
                    memory_sessions.c.session_id == session_id
                )
            )
            row = result.first()
        if row is None:
            return []
        messages = ModelMessagesTypeAdapter.validate_json(row[0])
        if limit is not None and limit > 0:
            messages = messages[-limit:]
        return messages

    async def save_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        # Full replace (last-writer-wins by design). The pre-read only decides
        # insert-vs-update so an existing row keeps its original created_at.
        await ensure_schema(self._engine)
        blob = ModelMessagesTypeAdapter.dump_json(list(messages))
        now = datetime.now().isoformat()
        async with self._engine.begin() as conn:
            exists = (
                await conn.execute(
                    select(memory_sessions.c.session_id).where(
                        memory_sessions.c.session_id == session_id
                    )
                )
            ).first()
            if exists:
                await conn.execute(
                    update(memory_sessions)
                    .where(memory_sessions.c.session_id == session_id)
                    .values(updated_at=now, message_count=len(messages), messages=blob)
                )
            else:
                await conn.execute(
                    insert(memory_sessions).values(
                        session_id=session_id,
                        user_id=_user_id_from_session(session_id),
                        created_at=now,
                        updated_at=now,
                        message_count=len(messages),
                        messages=blob,
                    )
                )

    async def append_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        # Atomic read-modify-write. The per-session lock serializes appenders in this
        # process (the SQLite single-instance model); FOR UPDATE locks the row on
        # Postgres (multi-instance). SQLite has no FOR UPDATE, so it's applied by
        # dialect. Together, concurrent appenders never clobber each other's turns.
        lock = await self._lock_for(session_id)
        async with lock:
            await ensure_schema(self._engine)
            now = datetime.now().isoformat()
            selector = select(memory_sessions.c.messages).where(
                memory_sessions.c.session_id == session_id
            )
            if self._engine.dialect.name != "sqlite":
                selector = selector.with_for_update()
            async with self._engine.begin() as conn:
                row = (await conn.execute(selector)).first()
                existing = ModelMessagesTypeAdapter.validate_json(row[0]) if row else []
                combined = existing + list(messages)
                blob = ModelMessagesTypeAdapter.dump_json(combined)
                if row is None:
                    await conn.execute(
                        insert(memory_sessions).values(
                            session_id=session_id,
                            user_id=_user_id_from_session(session_id),
                            created_at=now,
                            updated_at=now,
                            message_count=len(combined),
                            messages=blob,
                        )
                    )
                else:
                    await conn.execute(
                        update(memory_sessions)
                        .where(memory_sessions.c.session_id == session_id)
                        .values(updated_at=now, message_count=len(combined), messages=blob)
                    )

    async def clear_session(self, session_id: str) -> None:
        await ensure_schema(self._engine)
        async with self._engine.begin() as conn:
            await conn.execute(
                delete(memory_sessions).where(memory_sessions.c.session_id == session_id)
            )

    async def list_sessions(self) -> list[SessionMetadata]:
        await ensure_schema(self._engine)
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(*_SESSION_COLUMNS).order_by(memory_sessions.c.updated_at.desc())
            )
            rows = result.mappings().all()
        return [_to_metadata(r) for r in rows]

    async def get_metadata(self, session_id: str) -> SessionMetadata | None:
        await ensure_schema(self._engine)
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(*_SESSION_COLUMNS).where(memory_sessions.c.session_id == session_id)
            )
            row = result.mappings().first()
        return _to_metadata(row) if row else None
