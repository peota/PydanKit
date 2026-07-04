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

    # Cosmetic display name for this agent: shown on the dashboard, in the browser tab,
    # and as the API/Swagger title. Purely branding; defaults to the kit name.
    agent_name: str = "PydanKit"

    # Bound a single agent run so a misbehaving tool can't loop forever (cost/hang guard).
    agent_request_limit: int = 5

    # Observability
    logfire_token: str | None = None

    # Debug
    debug: bool = False

    # API server
    # Allowed CORS origins for the API. Default is restrictive; add your frontend origin(s).
    # Must NOT be ["*"]: credentials are always enabled on the API, and the app refuses
    # to start with a wildcard origin (it would leak the session cookie cross-site).
    cors_origins: list[str] = ["http://localhost:8000"]
    # Optional API key. When set, the API requires an "X-API-Key" header matching this value.
    # Legacy single-shared-secret gate. Superseded by per-user auth (see ADR 0001) when
    # AUTH_ENABLED=true; kept for machine-to-machine convenience.
    api_key: str | None = None
    # Expose interactive docs (/docs, /redoc, /openapi.json). None (default) follows
    # DEBUG: on in dev, OFF in production so the API surface isn't advertised. Set
    # true/false to force. Resolved by `docs_ui_enabled`.
    docs_enabled: bool | None = None

    # Authentication (ADR 0001). On by default: a fresh clone requires creating a
    # user before signing in to the dashboard (the login screen shows the command:
    # `python -m src.main users --add <name> --admin`). Set AUTH_ENABLED=false to run
    # open, in which case the API is unprotected and user_id falls back to the
    # request/anonymous value. (ADR 0001 recommends false; the shipped default is true.)
    auth_enabled: bool = True
    # Single SQLite database for users, tokens, and (optionally) conversation memory.
    # Legacy setting: kept as a back-compat alias. When DATABASE_URL is unset, a SQLite
    # URL is derived from this path (see `sqlalchemy_url`).
    database_path: str = "pydankit.db"
    # Full SQLAlchemy engine URL selecting the storage backend, e.g.:
    #   sqlite+aiosqlite:///./pydankit.db          (default, zero-config, light/local)
    #   postgresql+asyncpg://user:pass@host/db     (cloud / multi-instance)
    # Leave unset to fall back to a SQLite URL derived from DATABASE_PATH above.
    database_url: str | None = None
    # First-admin bootstrap for shell-less deploys (ADR 0002): if auth is on and no
    # admin exists yet, an admin with these credentials is created on startup. Leave
    # unset to skip. Rotate/clear the password after first login.
    admin_username: str | None = None
    admin_password: str | None = None
    # Dashboard session cookie lifetime (sliding: extended on activity).
    session_ttl_days: int = 7
    # Mark the session cookie Secure (HTTPS-only). Default false so the localhost
    # demo works over http; set true in any deployment served over TLS.
    session_cookie_secure: bool = False
    # Login brute-force throttle: lock out after N failures within the window.
    login_max_attempts: int = 5
    login_lockout_seconds: int = 300

    # Memory Configuration
    # memory_storage_type "auto" (default) follows the database: durable "sql" memory
    # when DATABASE_URL is explicitly set, else process-local "memory" (lost on restart,
    # not shared across workers). Force with "sql"/"memory"; "sqlite" = legacy alias for
    # "sql". Resolved by `effective_memory_backend`.
    memory_enabled: bool = True  # Enabled by default for better UX
    memory_storage_type: Literal["auto", "memory", "sql", "sqlite"] = "auto"
    memory_max_messages: int = 100
    memory_auto_session: bool = True  # Auto-generate session_id from user_id

    @property
    def effective_memory_backend(self) -> Literal["memory", "sql"]:
        """Resolve memory_storage_type to the concrete backend ("memory" or "sql").

        "auto" follows the database: durable "sql" when DATABASE_URL is explicitly set,
        else in-process "memory". "sqlite" is treated as "sql". Keeps the common case
        ("point at Postgres, everything persists") a single setting, while leaving
        "sql"/"memory" as explicit overrides (e.g. durable auth + ephemeral memory).
        """
        if self.memory_storage_type in ("sql", "sqlite"):
            return "sql"
        if self.memory_storage_type == "memory":
            return "memory"
        return "sql" if self.database_url is not None else "memory"

    @property
    def sqlalchemy_url(self) -> str:
        """Engine URL: explicit DATABASE_URL, else a SQLite URL from DATABASE_PATH.

        Keeps the legacy DATABASE_PATH working (including the /data volume path the
        deployment guide sets) while allowing a full Postgres URL for cloud.
        """
        if self.database_url:
            return self.database_url
        # Forward slashes so a Windows path (C:\...) still forms a valid SQLite URL.
        return f"sqlite+aiosqlite:///{self.database_path.replace(chr(92), '/')}"

    @property
    def docs_ui_enabled(self) -> bool:
        """Whether to serve Swagger/ReDoc/openapi.json. Defaults to DEBUG (off in prod)."""
        return self.debug if self.docs_enabled is None else self.docs_enabled


@lru_cache
def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()
