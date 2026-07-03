"""Shared test setup.

Tests never hit a real LLM (they use Pydantic AI's TestModel), but constructing
the agent still wants an API key present, so we set a dummy one.
"""

import asyncio
import os
import sys
import tempfile

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

# Keep the auth/memory SQLite DB out of the repo root: default DATABASE_PATH to a
# temp file for the whole session. Tests still override it via monkeypatch; undo()
# reverts to this temp path, never the repo root. (Module reloads across test files
# can otherwise leave the default path active and write ./pydankit.db.)
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.gettempdir(), "pydankit_test.db"))

# Match the app's Windows event-loop policy so async tests behave the same.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
