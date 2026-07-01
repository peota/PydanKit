"""Agent behavior tests using TestModel (no real LLM, no API key, offline).

These assert *structural* facts that hold regardless of the eventual use case:
the agent returns the declared output type, calls its tools, and injects deps.
"""

from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.test import TestModel

from src.agent import get_agent
from src.dependencies import AgentDeps


async def test_agent_returns_text():
    agent = get_agent()
    with agent.override(model=TestModel()):
        res = await agent.run("hello", deps=AgentDeps(memory_enabled=False))
    assert isinstance(res.output, str)
    assert res.output


async def test_tool_called_and_deps_injected():
    agent = get_agent()
    with capture_run_messages() as messages:
        with agent.override(model=TestModel()):
            await agent.run("hi", deps=AgentDeps(user_id="alice", memory_enabled=False))

    tool_calls = [p for m in messages for p in m.parts if isinstance(p, ToolCallPart)]
    tool_returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]

    # The agent selected the example tool...
    assert any(tc.tool_name == "example_tool" for tc in tool_calls)
    # ...and its dependencies were injected (example_tool embeds user_id in its result).
    assert any("alice" in str(tr.content) for tr in tool_returns)
