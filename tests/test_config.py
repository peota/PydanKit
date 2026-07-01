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


def test_defaults():
    s = Settings()
    assert s.memory_storage_type == "memory"
    assert s.cors_origins == ["http://localhost:8000"]
    assert s.api_key is None
