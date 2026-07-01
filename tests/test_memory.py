"""Memory tests, including the regression that motivated the rewrite."""

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel

from src.agent import get_agent
from src.dependencies import AgentDeps
from src.memory.manager import MemoryManager
from src.memory.storage import InMemoryStorage


async def _make_turn_with_tools():
    agent = get_agent()
    with agent.override(model=TestModel()):
        res = await agent.run("do something", deps=AgentDeps(memory_enabled=False))
    return res.new_messages()


async def test_history_preserves_tool_messages():
    """Regression: save_turn used to strip tool calls, which corrupted history
    (and, with a structured output_type, dropped the assistant's answer entirely).
    A turn that used tools must round-trip through storage intact."""
    new = await _make_turn_with_tools()
    assert any(isinstance(p, ToolCallPart) for m in new for p in m.parts), (
        "precondition: the turn should contain tool calls"
    )

    mm = MemoryManager(InMemoryStorage())
    await mm.save_turn(session_id="s1", new_messages=new)
    hist = await mm.get_history(session_id="s1")

    assert len(hist) == len(new)
    assert any(isinstance(p, ToolCallPart) for m in hist for p in m.parts)


async def test_clear_session():
    new = await _make_turn_with_tools()
    mm = MemoryManager(InMemoryStorage())
    await mm.save_turn(session_id="s2", new_messages=new)
    assert await mm.get_history(session_id="s2")

    await mm.clear_session("s2")
    assert await mm.get_history(session_id="s2") == []
