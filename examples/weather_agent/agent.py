"""Weather agent definition and execution."""

import logging
import os
from functools import lru_cache

import logfire
from pydantic_ai import Agent

from .config import WeatherSettings, get_settings
from .dependencies import WeatherDeps
from .models import WeatherResponse
from .tools import get_forecast, get_weather

logger = logging.getLogger(__name__)


def _configure_logging(settings: WeatherSettings) -> None:
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


def _configure_environment(settings: WeatherSettings) -> None:
    """Set environment variables from settings for pydantic-ai providers."""
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)


def _configure_logfire(settings: WeatherSettings) -> None:
    """Configure Logfire for observability."""
    if settings.logfire_token:
        logfire.configure(token=settings.logfire_token)
    else:
        logfire.configure(send_to_logfire=False)  # Local console output only
    logfire.instrument_pydantic_ai()


@lru_cache
def get_agent() -> Agent[WeatherDeps, WeatherResponse]:
    """Get or create the weather agent instance (lazy initialization)."""
    settings = get_settings()
    _configure_logging(settings)
    _configure_environment(settings)
    _configure_logfire(settings)

    agent = Agent(
        settings.model_name,
        deps_type=WeatherDeps,
        output_type=WeatherResponse,
        instructions=(
            "You are a helpful weather assistant. When users ask about weather:\n\n"
            "1. Use the get_weather tool to fetch current conditions\n"
            "2. Use the get_forecast tool when users ask about upcoming days\n"
            "3. Provide friendly, informative summaries of the weather\n\n"
            "Always include the location, temperature, and conditions in your response.\n"
            "If a city is not found, politely explain and suggest checking the spelling."
        ),
    )

    # Register tools
    agent.tool(get_weather)
    agent.tool(get_forecast)

    return agent


async def run_weather_agent(prompt: str, deps: WeatherDeps) -> WeatherResponse:
    """Run the weather agent with the given prompt.

    Args:
        prompt: User's weather query.
        deps: Dependencies including HTTP client.

    Returns:
        Structured weather response.
    """
    agent = get_agent()

    logger.debug("=" * 50)
    logger.debug("WEATHER AGENT REQUEST")
    logger.debug("=" * 50)
    logger.debug("Prompt: %s", prompt)

    result = await agent.run(prompt, deps=deps)

    logger.debug("-" * 50)
    logger.debug("WEATHER AGENT RESPONSE")
    logger.debug("-" * 50)
    logger.debug("Location: %s", result.output.location)
    logger.debug("Temperature: %s", result.output.temperature)
    logger.debug("Usage: %s", result.usage())
    logger.debug("=" * 50)

    return result.output


async def run_weather_agent_stream(prompt: str, deps: WeatherDeps):
    """Run the weather agent with streaming response.

    Args:
        prompt: User's weather query.
        deps: Dependencies including HTTP client.

    Yields:
        Streamed text chunks from the agent.
    """
    agent = get_agent()

    logger.debug("=" * 50)
    logger.debug("WEATHER AGENT STREAM REQUEST")
    logger.debug("=" * 50)
    logger.debug("Prompt: %s", prompt)

    last_content = ""
    async with agent.run_stream(prompt, deps=deps) as result:
        # For structured outputs, use stream_output() to get partial validated objects
        async for output in result.stream_output(debounce_by=0.05):
            # Extract the summary field and yield only new text (delta)
            current_content = output.summary or ""
            if current_content != last_content:
                # Yield only the new portion
                delta = current_content[len(last_content):]
                if delta:
                    yield delta
                last_content = current_content

    logger.debug("-" * 50)
    logger.debug("WEATHER AGENT STREAM COMPLETE")
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
    }
