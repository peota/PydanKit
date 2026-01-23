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


async def save_fact(ctx: RunContext[AgentDeps], key: str, value: str) -> str:
    """Save a fact for later retrieval.

    Use this when the user explicitly wants to remember something important
    for future conversations. Facts are stored persistently across sessions
    and can be retrieved later.

    Args:
        ctx: The run context containing dependencies
        key: A short identifier for the fact (e.g., "favorite_color", "birthday")
        value: The fact to remember

    Returns:
        Confirmation message
    """
    # Store in metadata (persisted with session)
    ctx.deps.metadata[f"fact:{key}"] = value
    return f"Remembered: {key} = {value}"


async def retrieve_facts(ctx: RunContext[AgentDeps]) -> str:
    """Retrieve all saved facts.

    Use this to recall information the user asked you to remember in previous
    conversations. This provides access to explicitly saved facts.

    Args:
        ctx: The run context containing dependencies

    Returns:
        JSON string of all saved facts, or a message if no facts are saved
    """
    import json

    facts = {
        k.replace("fact:", ""): v
        for k, v in (ctx.deps.metadata or {}).items()
        if k.startswith("fact:")
    }

    if not facts:
        return "No facts saved yet"

    return json.dumps(facts, indent=2)
