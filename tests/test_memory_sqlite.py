"""Tests for SqlMemoryStorage (ADR 0001, Phase 2) — offline, no API key.

Requires the ``[auth]`` extra (aiosqlite).
"""

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from src.memory.sql_storage import SqlMemoryStorage


def _turn(prompt: str, reply: str) -> list:
    """A minimal request/response pair, as Pydantic AI would produce."""
    return [
        ModelRequest(parts=[UserPromptPart(content=prompt)]),
        ModelResponse(parts=[TextPart(content=reply)]),
    ]


@pytest.fixture
async def store(db_engine):
    return SqlMemoryStorage(db_engine)


async def test_save_and_get_roundtrip(store):
    msgs = _turn("hello", "hi there")
    await store.save_messages("s1", msgs)
    loaded = await store.get_messages("s1")
    assert len(loaded) == 2
    assert loaded[0].parts[0].content == "hello"
    assert loaded[1].parts[0].content == "hi there"


async def test_missing_session_returns_empty(store):
    assert await store.get_messages("nope") == []
    assert await store.get_metadata("nope") is None


async def test_append_accumulates(store):
    await store.append_messages("s1", _turn("q1", "a1"))
    await store.append_messages("s1", _turn("q2", "a2"))
    loaded = await store.get_messages("s1")
    assert len(loaded) == 4
    assert loaded[-1].parts[0].content == "a2"


async def test_get_messages_limit_returns_most_recent(store):
    await store.append_messages("s1", _turn("q1", "a1"))
    await store.append_messages("s1", _turn("q2", "a2"))
    loaded = await store.get_messages("s1", limit=1)
    assert len(loaded) == 1
    assert loaded[0].parts[0].content == "a2"


async def test_clear_session(store):
    await store.save_messages("s1", _turn("x", "y"))
    await store.clear_session("s1")
    assert await store.get_messages("s1") == []
    assert await store.get_metadata("s1") is None


async def test_metadata_extracts_user_id_and_counts(store):
    await store.save_messages("user:alice", _turn("hi", "hey"))
    meta = await store.get_metadata("user:alice")
    assert meta is not None
    assert meta.user_id == "alice"
    assert meta.message_count == 2


async def test_list_sessions(store):
    await store.save_messages("user:alice", _turn("a", "b"))
    await store.save_messages("user:bob", _turn("c", "d"))
    sessions = await store.list_sessions()
    assert {s.session_id for s in sessions} == {"user:alice", "user:bob"}


async def test_concurrent_appends_do_not_lose_turns(store):
    """Atomic append: 20 concurrent single-turn appends all survive (no clobbering)."""
    import asyncio

    await asyncio.gather(*[store.append_messages("s1", _turn(f"q{i}", f"a{i}")) for i in range(20)])
    loaded = await store.get_messages("s1")
    assert len(loaded) == 40  # 20 turns * 2 messages each


async def test_persists_across_instances(db_engine):
    first = SqlMemoryStorage(db_engine)
    await first.save_messages("s1", _turn("remember", "ok"))
    # A fresh instance (e.g. another worker/process) sees the same data.
    second = SqlMemoryStorage(db_engine)
    loaded = await second.get_messages("s1")
    assert loaded[0].parts[0].content == "remember"
