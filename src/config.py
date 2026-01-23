"""Settings management using pydantic-settings."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM Configuration
    model_name: str = "openai:gpt-4o"
    openai_api_key: str = ""

    # Observability
    logfire_token: str | None = None

    # Debug
    debug: bool = False

    # Memory Configuration
    memory_enabled: bool = True  # Enabled by default for better UX
    memory_storage_type: Literal["memory", "file", "redis"] = "memory"
    memory_file_path: Path = Path(".memory")
    memory_redis_url: str | None = None
    memory_max_messages: int = 100
    memory_max_tokens: int | None = None
    memory_ttl_seconds: int | None = None
    memory_auto_session: bool = True  # Auto-generate session_id from user_id


def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()
