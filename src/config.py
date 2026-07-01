"""Settings management using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into the process environment so provider SDKs can read their own keys
# regardless of entry point (CLI or the uvicorn-loaded API). Pydantic AI is
# provider-agnostic: set MODEL_NAME to any supported model and provide that
# provider's standard key (e.g. OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY,
# DEEPSEEK_API_KEY, GEMINI_API_KEY). We do NOT model provider keys here on purpose.
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM Configuration. Provider-agnostic model string, e.g.:
    #   openai:gpt-4o | anthropic:claude-sonnet-4-5 | groq:llama-3.3-70b-versatile
    #   deepseek:deepseek-chat | google:gemini-2.0-flash
    # Pick a model your account can access and verify it exists before shipping.
    model_name: str = "openai:gpt-4o"

    # Bound a single agent run so a misbehaving tool can't loop forever (cost/hang guard).
    agent_request_limit: int = 5

    # Observability
    logfire_token: str | None = None

    # Debug
    debug: bool = False

    # API server
    # Allowed CORS origins for the API. Default is restrictive; add your frontend origin(s).
    # Set to ["*"] only if you understand the implications (and never with credentials).
    cors_origins: list[str] = ["http://localhost:8000"]
    # Optional API key. When set, the API requires an "X-API-Key" header matching this value.
    api_key: str | None = None

    # Memory Configuration
    # Storage is process-local and in-memory: history is lost on restart and is NOT
    # shared across API worker processes. Persist it by implementing MemoryStorage.
    memory_enabled: bool = True  # Enabled by default for better UX
    memory_storage_type: Literal["memory"] = "memory"
    memory_max_messages: int = 100
    memory_auto_session: bool = True  # Auto-generate session_id from user_id


@lru_cache
def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()
