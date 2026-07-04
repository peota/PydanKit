"""Plumbing: settings load from the environment."""

from src.config import Settings


def test_env_vars_override(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "openai:gpt-4o-mini")
    monkeypatch.setenv("AGENT_REQUEST_LIMIT", "3")
    monkeypatch.setenv("MEMORY_ENABLED", "false")
    s = Settings()
    assert s.model_name == "openai:gpt-4o-mini"
    assert s.agent_request_limit == 3
    assert s.memory_enabled is False


def test_defaults(monkeypatch):
    # Ignore any developer .env AND the conftest session pins, to assert code defaults.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MEMORY_STORAGE_TYPE", raising=False)
    s = Settings(_env_file=None)
    assert s.memory_storage_type == "auto"
    assert s.effective_memory_backend == "memory"  # no DATABASE_URL configured
    assert s.cors_origins == ["http://localhost:8000"]
    assert s.api_key is None


def test_memory_backend_auto_follows_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MEMORY_STORAGE_TYPE", raising=False)
    # auto + no DATABASE_URL -> in-process memory
    assert Settings(_env_file=None).effective_memory_backend == "memory"
    # auto + DATABASE_URL set -> durable sql (the common "point at Postgres" case)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    assert Settings(_env_file=None).effective_memory_backend == "sql"


def test_memory_backend_explicit_overrides(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    # explicit "memory" wins even with a database (durable auth + ephemeral memory)
    monkeypatch.setenv("MEMORY_STORAGE_TYPE", "memory")
    assert Settings(_env_file=None).effective_memory_backend == "memory"
    # "sqlite" remains a legacy alias for "sql"
    monkeypatch.setenv("MEMORY_STORAGE_TYPE", "sqlite")
    assert Settings(_env_file=None).effective_memory_backend == "sql"
