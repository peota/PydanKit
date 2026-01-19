"""Settings management using pydantic-settings."""

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


def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()
