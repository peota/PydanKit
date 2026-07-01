"""Shared test setup.

Tests never hit a real LLM (they use Pydantic AI's TestModel), but constructing
the agent still wants an API key present, so we set a dummy one.
"""

import asyncio
import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

# Match the app's Windows event-loop policy so async tests behave the same.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
