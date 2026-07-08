"""System routes: dashboard page, health check, and agent metadata."""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.agent import get_agent_info
from src.api.common import APP_VERSION, STATIC_DIR, sanitize_error
from src.auth.db import User
from src.auth.dependencies import get_current_user
from src.config import get_settings

router = APIRouter(tags=["System"])


class HealthResponse(BaseModel):
    """Response body for health check."""

    status: str
    name: str
    model: str
    version: str


class InfoResponse(BaseModel):
    """Response body for info endpoint."""

    model: str
    tools: list[str]
    debug: bool
    logfire_enabled: bool
    memory_enabled: bool = False
    memory_storage_type: str | None = None
    memory_max_messages: int | None = None
    # The signed-in username when auth is enabled; None when auth is off. Lets the
    # dashboard show the account and decide whether to render a logout control.
    authenticated_user: str | None = None
    # Whether the signed-in user is an admin (drives the admin panel visibility).
    is_admin: bool = False
    error: str | None = None


@router.get("/", response_class=FileResponse)
async def dashboard() -> FileResponse:
    """Serve the dashboard page."""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        name=settings.agent_name,
        model=settings.model_name,
        version=APP_VERSION,
    )


@router.get("/info", response_model=InfoResponse)
async def info(user: User | None = Depends(get_current_user)) -> InfoResponse:
    """Get agent configuration and metadata (auth-required when enabled)."""
    settings = get_settings()
    username = user.username if user else None
    is_admin = bool(user and user.is_admin)
    try:
        agent_info = get_agent_info()
        return InfoResponse(**agent_info, authenticated_user=username, is_admin=is_admin)
    except Exception as e:
        # Return partial info with error message for configuration issues
        return InfoResponse(
            model=settings.model_name,
            tools=[],
            debug=settings.debug,
            logfire_enabled=bool(settings.logfire_token),
            memory_enabled=settings.memory_enabled,
            memory_storage_type=settings.effective_memory_backend,
            memory_max_messages=settings.memory_max_messages,
            authenticated_user=username,
            is_admin=is_admin,
            error=sanitize_error(e, "info"),
        )
