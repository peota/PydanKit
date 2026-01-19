"""Tool definitions for the agent.

Tools allow the agent to perform actions and retrieve information.
Each tool should have a clear docstring that explains what it does,
as the LLM uses this to decide when to call the tool.
"""

from pydantic_ai import RunContext

from src.dependencies import AgentDeps


async def example_tool(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search for information based on a query.

    This is an example tool - replace with your actual tools.
    The docstring is used by the LLM to understand when to use this tool.

    Args:
        ctx: The run context containing dependencies
        query: The search query

    Returns:
        The search result as a string
    """
    # Access dependencies via ctx.deps
    user_id = ctx.deps.user_id or "anonymous"
    return f"[User: {user_id}] Result for query: {query}"


async def get_current_time(ctx: RunContext[AgentDeps]) -> str:
    """Get the current date and time.

    Use this tool when the user asks about the current time or date.
    """
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
