"""Shared test setup.

Tests never hit a real LLM (they use Pydantic AI's TestModel), but constructing
the agent still wants an API key present, so we set a dummy one.
"""

import asyncio
import os
import sys
import tempfile

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

# Keep the auth/memory DB out of the repo root AND hermetic from any developer .env:
# pin a temp SQLite DATABASE_URL + in-process memory for the whole session. Env vars
# outrank .env, so a real DATABASE_URL / Postgres in the developer's .env can't leak
# into the tests. Per-test fixtures override DATABASE_URL for isolation.
_test_db = os.path.join(tempfile.gettempdir(), "pydankit_test.db").replace(chr(92), "/")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_test_db}")
os.environ.setdefault("MEMORY_STORAGE_TYPE", "memory")

# Tests configure the app purely through os.environ (which they monkeypatch). Stop
# pydantic-settings from ALSO reading the developer's real .env file at instantiation,
# so a value a test deletes (e.g. monkeypatch.delenv("DOCS_ENABLED")) actually stays
# gone instead of being silently re-read from .env. Production is unaffected — this
# only mutates the in-process Settings class during the test session.
from src.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None

# Match the app's Windows event-loop policy so async tests behave the same.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
async def db_engine(tmp_path):
    """Async engine for the auth/memory store tests.

    Defaults to an isolated temp SQLite file. If ``POSTGRES_TEST_URL`` is set (the CI
    Postgres job), it runs against real Postgres with a clean schema per test — so the
    same store tests prove *both* dialects with no duplicated test bodies.
    """
    from src.db import create_engine_from_url, metadata

    url = os.environ.get("POSTGRES_TEST_URL")
    if url:
        engine = create_engine_from_url(url)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
            await conn.run_sync(metadata.create_all)
    else:
        path = str(tmp_path / "test.db").replace("\\", "/")
        engine = create_engine_from_url(f"sqlite+aiosqlite:///{path}")
    yield engine
    await engine.dispose()
