"""Unit tests for context-window trimming."""

from pydantic_ai.messages import ModelRequest, UserPromptPart

from src.memory.processors import truncate_by_message_count


def _msgs(n: int):
    return [ModelRequest(parts=[UserPromptPart(content=f"m{i}")]) for i in range(n)]


def test_truncate_keeps_most_recent():
    msgs = _msgs(10)
    out = truncate_by_message_count(msgs, 3)
    assert len(out) == 3
    assert out == msgs[-3:]


def test_truncate_noop_when_under_cap():
    msgs = _msgs(2)
    assert truncate_by_message_count(msgs, 5) == msgs
