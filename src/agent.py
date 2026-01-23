"""Agent definition and execution."""

import logging
import os
from functools import lru_cache

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from src.config import Settings, get_settings
from src.dependencies import AgentDeps
from src.memory.manager import get_memory_manager
from src.models import AgentResponse
from src.tools import example_tool, get_current_time, retrieve_facts, save_fact

logger = logging.getLogger(__name__)


def _configure_logging(settings: Settings) -> None:
    """Configure logging based on debug setting."""
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Set pydantic_ai logger to same level for detailed output
    logging.getLogger("pydantic_ai").setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING if not settings.debug else logging.DEBUG)

    if settings.debug:
        logger.debug("Debug mode enabled - verbose logging active")


def _configure_environment(settings: Settings) -> None:
    """Set environment variables from settings for pydantic-ai providers."""
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)


def _configure_logfire(settings: Settings) -> None:
    """Configure Logfire for observability."""
    if settings.logfire_token:
        logfire.configure(token=settings.logfire_token)
    else:
        logfire.configure(send_to_logfire=False)  # Local console output only
    logfire.instrument_pydantic_ai()


@lru_cache
def get_agent() -> Agent[AgentDeps, AgentResponse]:
    """Get or create the agent instance (lazy initialization)."""
    settings = get_settings()
    _configure_logging(settings)
    _configure_environment(settings)
    _configure_logfire(settings)

    agent = Agent(
        settings.model_name,
        deps_type=AgentDeps,
        output_type=AgentResponse,
        instructions=(
            "You are a helpful assistant. Customize this prompt for your specific use case.\n\n"
            "When responding:\n"
            "- Be concise and helpful\n"
            "- Use tools when appropriate\n"
            "- Provide a confidence score when you can estimate your certainty\n\n"
            "You can extend these instructions or make them dynamic using "
            "@agent.instructions decorator."
        ),
    )

    # Register tools
    agent.tool(example_tool)
    agent.tool(get_current_time)
    agent.tool(save_fact)
    agent.tool(retrieve_facts)

    return agent


async def run_agent(
    prompt: str, deps: AgentDeps | None = None, message_history: list[ModelMessage] | None = None
) -> AgentResponse:
    """Run the agent with given prompt and dependencies.

    Args:
        prompt: The user's input prompt
        deps: Optional dependencies (creates default if not provided)
        message_history: Optional conversation history (loaded from memory if not provided)

    Returns:
        The agent's structured response
    """
    agent = get_agent()
    deps = deps or AgentDeps()

    # Load message history from memory if not provided
    if message_history is None and deps.memory_enabled:
        memory_manager = get_memory_manager()
        message_history = await memory_manager.get_history(
            session_id=deps.session_id, user_id=deps.user_id
        )
        logger.debug("Loaded %d messages from memory for session", len(message_history))

    logger.debug("=" * 50)
    logger.debug("AGENT REQUEST")
    logger.debug("=" * 50)
    logger.debug("Prompt: %s", prompt)
    logger.debug("User ID: %s", deps.user_id)
    logger.debug("Session ID: %s", deps.session_id)
    logger.debug("History size: %d messages", len(message_history) if message_history else 0)

    result = await agent.run(prompt, deps=deps, message_history=message_history)

    # Save conversation to memory
    if deps.memory_enabled:
        memory_manager = get_memory_manager()
        new_messages = result.new_messages()
        await memory_manager.save_turn(
            session_id=deps.session_id, new_messages=new_messages, user_id=deps.user_id
        )
        logger.debug("Saved %d new messages to memory", len(new_messages))

    logger.debug("-" * 50)
    logger.debug("AGENT RESPONSE")
    logger.debug("-" * 50)
    logger.debug("Content: %s", result.output.content)
    logger.debug("Confidence: %s", result.output.confidence)
    logger.debug("Usage: %s", result.usage())
    logger.debug("=" * 50)

    return result.output


async def run_agent_text(prompt: str, deps: AgentDeps | None = None) -> str:
    """Run the agent and return just the text content.

    Convenience function for simple text-only responses.
    """
    response = await run_agent(prompt, deps)
    return response.content


async def run_agent_stream(
    prompt: str, deps: AgentDeps | None = None, message_history: list[ModelMessage] | None = None
):
    """Run the agent with streaming response.

    Args:
        prompt: The user's input prompt
        deps: Optional dependencies (creates default if not provided)
        message_history: Optional conversation history (loaded from memory if not provided)

    Yields:
        Streamed text chunks from the agent
    """
    agent = get_agent()
    deps = deps or AgentDeps()

    # Load message history from memory if not provided
    if message_history is None and deps.memory_enabled:
        memory_manager = get_memory_manager()
        message_history = await memory_manager.get_history(
            session_id=deps.session_id, user_id=deps.user_id
        )
        logger.debug("Loaded %d messages from memory for session", len(message_history))

    logger.debug("=" * 50)
    logger.debug("AGENT STREAM REQUEST")
    logger.debug("=" * 50)
    logger.debug("Prompt: %s", prompt)
    logger.debug("User ID: %s", deps.user_id)
    logger.debug("Session ID: %s", deps.session_id)
    logger.debug("History size: %d messages", len(message_history) if message_history else 0)

    last_content = ""
    async with agent.run_stream(prompt, deps=deps, message_history=message_history) as result:
        # For structured outputs, use stream_output() to get partial validated objects
        async for output in result.stream_output(debounce_by=0.05):
            # Extract the content field and yield only new text (delta)
            current_content = output.content
            if current_content != last_content:
                # Yield only the new portion
                delta = current_content[len(last_content):]
                if delta:
                    yield delta
                last_content = current_content

    # Save conversation to memory after stream completes
    if deps.memory_enabled:
        memory_manager = get_memory_manager()
        new_messages = result.new_messages()
        await memory_manager.save_turn(
            session_id=deps.session_id, new_messages=new_messages, user_id=deps.user_id
        )
        logger.debug("Saved %d new messages to memory", len(new_messages))

    logger.debug("-" * 50)
    logger.debug("AGENT STREAM COMPLETE")
    logger.debug("-" * 50)
    logger.debug("Usage: %s", result.usage())
    logger.debug("=" * 50)


def get_agent_info() -> dict:
    """Get agent metadata for dashboard display."""
    agent = get_agent()
    settings = get_settings()

    # Get tool names dynamically from agent's registered tools
    tool_names = list(agent._function_toolset.tools.keys())

    return {
        "model": settings.model_name,
        "tools": tool_names,
        "debug": settings.debug,
        "logfire_enabled": settings.logfire_token is not None,
        "memory_enabled": settings.memory_enabled,
        "memory_storage_type": settings.memory_storage_type,
        "memory_max_messages": settings.memory_max_messages,
    }
