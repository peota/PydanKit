"""FastAPI server for the agent (optional feature).

Install with: pip install -e ".[api]"
Run with: python -m src.main serve
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

try:
    from fastapi import Depends, FastAPI, HTTPException, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    raise ImportError("FastAPI is not installed. Install it with: pip install -e '.[api]'")

import logging
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field

from src.agent import get_agent_info, run_agent, run_agent_stream
from src.auth.db import User, UsernameTakenError
from src.auth.dependencies import (
    SESSION_COOKIE,
    clear_session_cookie,
    get_auth_store,
    get_current_user,
    require_admin,
    set_session_cookie,
)
from src.auth.tokens import hash_token
from src.config import get_settings
from src.dependencies import AgentDeps
from src.memory.manager import get_memory_manager
from src.memory.models import MemoryStats, SessionMetadata

STATIC_DIR = Path(__file__).parent / "static"

try:
    APP_VERSION = _pkg_version("PydanKit")
except PackageNotFoundError:
    APP_VERSION = "0.0.0+dev"

settings = get_settings()
logger = logging.getLogger(__name__)


def sanitize_error(e: Exception, context: str = "request") -> str:
    """Log error details internally and return a safe message for clients."""
    logger.error(f"Error during {context}: {type(e).__name__}: {e}")
    if settings.debug:
        return f"{type(e).__name__}: {e}"
    return "An internal error occurred. Please try again later."


@asynccontextmanager
async def _lifespan(_app: "FastAPI"):
    """Seed the first admin from the environment on a shell-less deploy (ADR 0002).

    Only runs when auth is on, ADMIN_USERNAME/ADMIN_PASSWORD are set, and no admin
    exists yet. Idempotent — a no-op once an admin is present.
    """
    if settings.auth_enabled and settings.admin_username and settings.admin_password:
        store = get_auth_store()
        if not await store.has_admin():
            try:
                await store.create_user(
                    settings.admin_username, settings.admin_password, is_admin=True
                )
                logger.info("Seeded initial admin '%s' from environment", settings.admin_username)
            except Exception as e:  # never block startup on a seed hiccup
                logger.warning("Admin env-seed skipped: %s", e)

    # Auth is durable (SQLite) but the default memory backend is process-local. Under
    # multiple workers that's a silent inconsistency — warn rather than surprise.
    if (
        settings.auth_enabled
        and settings.memory_enabled
        and settings.memory_storage_type == "memory"
    ):
        logger.warning(
            "Memory backend is 'memory' (process-local, lost on restart, not shared "
            "across workers) while auth is enabled. Set MEMORY_STORAGE_TYPE=sqlite for "
            "durable, worker-shared conversation history."
        )
    yield


app = FastAPI(
    title="Pydantic AI Agent API",
    description="REST API for the Pydantic AI Agent",
    version=APP_VERSION,
    lifespan=_lifespan,
)

# Configure CORS from settings (default is a localhost allowlist, not "*").
# Credentials are enabled so the session cookie works cross-origin from allowed
# origins. The spec forbids credentials + wildcard: Starlette would reflect the
# caller's Origin and set Allow-Credentials, letting any site ride the victim's
# cookie. Fail fast rather than trust a comment.
if "*" in settings.cors_origins:
    raise ValueError(
        "CORS_ORIGINS must not contain '*': credentials are enabled, so a wildcard "
        "origin is a credential-leak vector. Set explicit origins."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Requested-With"],
)


@app.middleware("http")
async def _no_cache_dashboard(request, call_next):
    """Serve the dashboard and its assets without caching.

    This is a dev/demo dashboard: edits to the HTML/JS should show up on reload,
    not be shadowed by the browser's heuristic cache.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


class ChatRequest(BaseModel):
    """Request body for chat endpoint.

    ``user_id`` is intentionally absent (ADR 0001): when auth is enabled the caller's
    identity comes from their credential, never the request body. When auth is
    disabled, ``session_id`` provides conversation continuity as before.
    """

    prompt: str = Field(
        ..., min_length=1, max_length=10000, description="The prompt to send to the agent"
    )
    session_id: str | None = Field(
        default=None,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_:-]*$",
        description="Session ID for conversation context (ignored when authenticated)",
    )
    memory_enabled: bool = Field(
        default=True,
        description="Enable memory for this request (default: true)",
    )


class LoginRequest(BaseModel):
    """Request body for the login endpoint."""

    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    """Response body for a successful login."""

    username: str
    is_admin: bool


def _deps_for(user: User | None, request: ChatRequest) -> AgentDeps:
    """Build AgentDeps, scoping memory to the authenticated user when present.

    Authenticated: identity = username, pinned to session ``user:<username>`` (the
    request's session_id is ignored — see ADR 0001, one session per user in v1).
    Anonymous (auth off): the request's session_id drives continuity as before.
    """
    if user is not None:
        # Pin the session explicitly (not via auto-session) so memory works even when
        # MEMORY_AUTO_SESSION is false. Matches the `user:<username>` ownership scheme.
        return AgentDeps(
            user_id=user.username,
            session_id=f"user:{user.username}",
            memory_enabled=request.memory_enabled,
        )
    return AgentDeps(
        user_id=None, session_id=request.session_id, memory_enabled=request.memory_enabled
    )


def _owns_session(user: User | None, metadata: SessionMetadata) -> bool:
    """A data route is in-bounds if auth is off, or the session is the caller's."""
    return user is None or metadata.user_id == user.username


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    content: str = Field(..., description="The agent's response")


class HealthResponse(BaseModel):
    """Response body for health check."""

    status: str
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


class SessionListResponse(BaseModel):
    """Response body for sessions list endpoint."""

    sessions: list[SessionMetadata]


class SessionDetailResponse(BaseModel):
    """Response body for session detail endpoint."""

    session: SessionMetadata


class SessionClearResponse(BaseModel):
    """Response body for session clear endpoint."""

    status: str
    session_id: str


@app.get("/", response_class=FileResponse)
async def dashboard() -> FileResponse:
    """Serve the dashboard page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", model=settings.model_name, version=APP_VERSION)


@app.get("/info", response_model=InfoResponse)
async def info(user: User | None = Depends(get_current_user)) -> InfoResponse:
    """Get agent configuration and metadata (auth-required when enabled)."""
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
            memory_storage_type=settings.memory_storage_type,
            memory_max_messages=settings.memory_max_messages,
            authenticated_user=username,
            is_admin=is_admin,
            error=sanitize_error(e, "info"),
        )


@app.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response) -> LoginResponse:
    """Verify a password and set an HttpOnly session cookie.

    Only meaningful when AUTH_ENABLED is true. Applies a per-username brute-force
    lockout (ADR 0001).
    """
    if not settings.auth_enabled:
        raise HTTPException(status_code=400, detail="Authentication is disabled")

    store = get_auth_store()
    if await store.is_locked_out(
        body.username, settings.login_max_attempts, settings.login_lockout_seconds
    ):
        raise HTTPException(status_code=429, detail="Too many attempts; try again later")

    user = await store.verify_login(body.username, body.password)
    if user is None:
        await store.record_failure(body.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    await store.clear_failures(body.username)
    ttl = settings.session_ttl_days * 86400
    token = await store.issue_token(user.id, "session", name="dashboard", ttl_seconds=ttl)
    set_session_cookie(response, token, ttl)
    return LoginResponse(username=user.username, is_admin=user.is_admin)


@app.post("/auth/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Revoke the current session token and clear the cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await get_auth_store().revoke_token(token)
    clear_session_cookie(response)
    return {"status": "logged out"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: User | None = Depends(get_current_user)) -> ChatResponse:
    """Send a prompt to the agent and get a response."""
    try:
        content = await run_agent(request.prompt, _deps_for(user, request))
        return ChatResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "chat"))


@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest, user: User | None = Depends(get_current_user)
) -> StreamingResponse:
    """Send a prompt to the agent and get a streaming response."""
    try:
        deps = _deps_for(user, request)

        async def event_generator():
            """Generate Server-Sent Events for streaming."""
            try:
                async for chunk in run_agent_stream(request.prompt, deps):
                    # Send each chunk as a data event
                    yield f"data: {chunk}\n\n"
                # Send completion signal
                yield "data: [DONE]\n\n"
            except Exception as e:
                # Send error event
                yield f"event: error\ndata: {sanitize_error(e, 'chat stream')}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "chat stream"))


@app.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user: User | None = Depends(get_current_user),
) -> SessionListResponse:
    """List conversation sessions (scoped to the caller when authenticated)."""
    if not settings.memory_enabled:
        return SessionListResponse(sessions=[])

    try:
        memory_manager = get_memory_manager()
        sessions = await memory_manager.list_sessions()
        if user is not None:
            sessions = [s for s in sessions if s.user_id == user.username]
        return SessionListResponse(sessions=sessions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "list sessions"))


@app.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str, user: User | None = Depends(get_current_user)
) -> SessionDetailResponse:
    """Get details for a specific session (only the caller's when authenticated)."""
    if not settings.memory_enabled:
        raise HTTPException(status_code=404, detail="Memory is disabled")

    try:
        memory_manager = get_memory_manager()
        metadata = await memory_manager.get_session_metadata(session_id)

        # Return the same 404 for "absent" and "not yours" so ownership isn't leaked.
        if metadata is None or not _owns_session(user, metadata):
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        return SessionDetailResponse(session=metadata)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "get session"))


@app.delete("/sessions/{session_id}", response_model=SessionClearResponse)
async def clear_session(
    session_id: str, user: User | None = Depends(get_current_user)
) -> SessionClearResponse:
    """Clear conversation history for a session (only the caller's when authenticated)."""
    if not settings.memory_enabled:
        raise HTTPException(status_code=404, detail="Memory is disabled")

    try:
        memory_manager = get_memory_manager()
        if user is not None:
            metadata = await memory_manager.get_session_metadata(session_id)
            if metadata is None or not _owns_session(user, metadata):
                raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        await memory_manager.clear_session(session_id)
        return SessionClearResponse(status="cleared", session_id=session_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "clear session"))


@app.get("/memory/stats", response_model=MemoryStats)
async def memory_stats(user: User | None = Depends(get_current_user)) -> MemoryStats:
    """Get memory system statistics (scoped to the caller when authenticated)."""
    try:
        memory_manager = get_memory_manager()
        if user is None:
            return await memory_manager.get_stats()
        # Scope counts to the caller's own sessions.
        own = [s for s in await memory_manager.list_sessions() if s.user_id == user.username]
        return MemoryStats(
            enabled=settings.memory_enabled,
            storage_type=settings.memory_storage_type,
            total_sessions=len(own),
            total_messages=sum(s.message_count for s in own),
            max_messages=settings.memory_max_messages,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "memory stats"))


# ---------------------------------------------------------------------------
# Admin: service accounts & API keys (ADR 0002). All routes require an admin;
# require_admin returns 404 when auth is disabled (no admin identity exists).
# ---------------------------------------------------------------------------


class CreateServiceAccountRequest(BaseModel):
    """Create a passwordless, non-admin service account."""

    username: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")


class AdminUserResponse(BaseModel):
    """A user as seen by the admin panel (never includes a password/secret)."""

    id: int
    username: str
    is_admin: bool
    disabled: bool
    is_service: bool
    created_at: float


class IssueKeyRequest(BaseModel):
    """Issue an API key for a service account; optional human label."""

    name: str | None = Field(default=None, max_length=128)


class IssuedKeyResponse(BaseModel):
    """Returned once when a key is minted — carries the plaintext key."""

    token_hash: str
    name: str | None
    key: str = Field(..., description="Plaintext key — shown once, store it now")


class AdminKeyResponse(BaseModel):
    """Key metadata for listing (never the plaintext value)."""

    token_hash: str
    name: str | None
    created_at: float
    expires_at: float | None


def _to_admin_user(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        disabled=user.disabled,
        is_service=user.is_service,
        created_at=user.created_at,
    )


@app.post("/admin/users", response_model=AdminUserResponse, status_code=201)
async def admin_create_service_account(
    body: CreateServiceAccountRequest, _admin: User = Depends(require_admin)
) -> AdminUserResponse:
    """Create a non-admin, passwordless service account (holds API keys, can't log in)."""
    store = get_auth_store()
    try:
        user = await store.create_service_account(body.username)
    except UsernameTakenError:
        raise HTTPException(status_code=409, detail=f"Username already exists: {body.username}")
    return _to_admin_user(user)


@app.get("/admin/users", response_model=list[AdminUserResponse])
async def admin_list_users(_admin: User = Depends(require_admin)) -> list[AdminUserResponse]:
    """List all accounts (admins, humans, and service accounts)."""
    users = await get_auth_store().list_users()
    return [_to_admin_user(u) for u in users]


async def _require_managed_user(user_id: int) -> User:
    """Load a user for admin ops, or 404. (Read-only routes may use any user.)"""
    user = await get_auth_store().get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    return user


async def _require_non_admin_user(user_id: int) -> User:
    """Load a user for admin MUTATIONS, rejecting admin accounts (ADR 0002).

    Admin accounts are never managed from the UI: issuing an admin an API key would
    mint a non-expiring, admin-privileged credential that bypasses the cookie/CSRF
    path — the escalation this endpoint must not enable.
    """
    user = await _require_managed_user(user_id)
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Admin accounts cannot be managed from the UI")
    return user


@app.post("/admin/users/{user_id}/keys", response_model=IssuedKeyResponse, status_code=201)
async def admin_issue_key(
    user_id: int, body: IssueKeyRequest, _admin: User = Depends(require_admin)
) -> IssuedKeyResponse:
    """Issue an API key for a non-admin account. Plaintext returned once, never stored."""
    user = await _require_non_admin_user(user_id)
    store = get_auth_store()
    key = await store.issue_token(user.id, "api_key", name=body.name)
    return IssuedKeyResponse(token_hash=hash_token(key), name=body.name, key=key)


@app.get("/admin/users/{user_id}/keys", response_model=list[AdminKeyResponse])
async def admin_list_keys(
    user_id: int, _admin: User = Depends(require_admin)
) -> list[AdminKeyResponse]:
    """List a user's active API keys (metadata only — the value is never re-shown)."""
    user = await _require_managed_user(user_id)
    tokens = await get_auth_store().list_tokens(user.id, kind="api_key")
    return [
        AdminKeyResponse(
            token_hash=t.token_hash, name=t.name, created_at=t.created_at, expires_at=t.expires_at
        )
        for t in tokens
    ]


@app.delete("/admin/keys/{token_hash}", response_model=SessionClearResponse)
async def admin_revoke_key(
    token_hash: str, _admin: User = Depends(require_admin)
) -> SessionClearResponse:
    """Revoke a key by its hash handle (rotation). 404 if it doesn't exist / already revoked."""
    revoked = await get_auth_store().revoke_token_by_hash(token_hash)
    if not revoked:
        raise HTTPException(status_code=404, detail="Key not found or already revoked")
    return SessionClearResponse(status="revoked", session_id=token_hash)


async def _set_disabled(user_id: int, disabled: bool) -> AdminUserResponse:
    """Toggle a non-admin account's disabled flag. Admin accounts aren't UI-managed.

    Disabling freezes the account and all its keys (auth resolution rejects a disabled
    owner); it does not revoke or delete keys. Enabling restores them unchanged.
    """
    user = await _require_non_admin_user(user_id)
    store = get_auth_store()
    await store.set_disabled(user.id, disabled)
    return _to_admin_user(await store.get_user_by_id(user.id))


@app.post("/admin/users/{user_id}/disable", response_model=AdminUserResponse)
async def admin_disable_user(
    user_id: int, _admin: User = Depends(require_admin)
) -> AdminUserResponse:
    """Disable a non-admin account (freezes it and its keys; reversible)."""
    return await _set_disabled(user_id, True)


@app.post("/admin/users/{user_id}/enable", response_model=AdminUserResponse)
async def admin_enable_user(
    user_id: int, _admin: User = Depends(require_admin)
) -> AdminUserResponse:
    """Re-enable a disabled non-admin account; its existing keys work again."""
    return await _set_disabled(user_id, False)


# Mount static files at the end after all routes are defined
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
