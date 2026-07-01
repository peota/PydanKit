"""FastAPI server for the agent (optional feature).

Install with: pip install -e ".[api]"
Run with: python -m src.main serve
"""

from pathlib import Path

try:
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    raise ImportError("FastAPI is not installed. Install it with: pip install -e '.[api]'")

import logging

from pydantic import BaseModel, Field

from src.agent import get_agent_info, run_agent, run_agent_stream
from src.config import get_settings
from src.dependencies import AgentDeps
from src.memory.manager import get_memory_manager
from src.memory.models import MemoryStats, SessionMetadata

STATIC_DIR = Path(__file__).parent / "static"

settings = get_settings()
logger = logging.getLogger(__name__)


def sanitize_error(e: Exception, context: str = "request") -> str:
    """Log error details internally and return a safe message for clients."""
    logger.error(f"Error during {context}: {type(e).__name__}: {e}")
    if settings.debug:
        return f"{type(e).__name__}: {e}"
    return "An internal error occurred. Please try again later."


app = FastAPI(
    title="Pydantic AI Agent API",
    description="REST API for the Pydantic AI Agent",
    version="0.1.0",
)

# Configure CORS from settings (default is a localhost allowlist, not "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional API-key gate.

    A no-op unless ``API_KEY`` is set in the environment. When set, protected
    endpoints require a matching ``X-API-Key`` header. This is a minimal seam,
    not a full auth system - swap in OAuth/JWT for real deployments.
    """
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    prompt: str = Field(
        ..., min_length=1, max_length=10000, description="The prompt to send to the agent"
    )
    user_id: str | None = Field(
        default=None,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_-]*$",
        description="Optional user ID for context",
    )
    session_id: str | None = Field(
        default=None,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_:-]*$",
        description="Session ID for conversation context",
    )
    memory_enabled: bool = Field(
        default=True,
        description="Enable memory for this request (default: true)",
    )


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    content: str = Field(..., description="The agent's response")


class HealthResponse(BaseModel):
    """Response body for health check."""

    status: str
    model: str


class InfoResponse(BaseModel):
    """Response body for info endpoint."""

    model: str
    tools: list[str]
    debug: bool
    logfire_enabled: bool
    memory_enabled: bool = False
    memory_storage_type: str | None = None
    memory_max_messages: int | None = None
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
    return HealthResponse(status="healthy", model=settings.model_name)


@app.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    """Get agent configuration and metadata."""
    try:
        agent_info = get_agent_info()
        return InfoResponse(**agent_info)
    except Exception as e:
        # Return partial info with error message for configuration issues
        return InfoResponse(
            model=settings.model_name,
            tools=[],
            debug=settings.debug,
            logfire_enabled=settings.logfire_token is not None,
            memory_enabled=settings.memory_enabled,
            memory_storage_type=settings.memory_storage_type,
            memory_max_messages=settings.memory_max_messages,
            error=sanitize_error(e, "info"),
        )


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a prompt to the agent and get a response."""
    try:
        deps = AgentDeps(
            user_id=request.user_id,
            session_id=request.session_id,
            memory_enabled=request.memory_enabled,
        )
        content = await run_agent(request.prompt, deps)
        return ChatResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "chat"))


@app.post("/chat/stream", dependencies=[Depends(require_api_key)])
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Send a prompt to the agent and get a streaming response."""
    try:
        deps = AgentDeps(
            user_id=request.user_id,
            session_id=request.session_id,
            memory_enabled=request.memory_enabled,
        )

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


@app.get(
    "/sessions",
    response_model=SessionListResponse,
    dependencies=[Depends(require_api_key)],
)
async def list_sessions() -> SessionListResponse:
    """List all conversation sessions."""
    if not settings.memory_enabled:
        return SessionListResponse(sessions=[])

    try:
        memory_manager = get_memory_manager()
        sessions = await memory_manager.list_sessions()
        return SessionListResponse(sessions=sessions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "list sessions"))


@app.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_session(session_id: str) -> SessionDetailResponse:
    """Get details for a specific session."""
    if not settings.memory_enabled:
        raise HTTPException(status_code=404, detail="Memory is disabled")

    try:
        memory_manager = get_memory_manager()
        metadata = await memory_manager.get_session_metadata(session_id)

        if metadata is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        return SessionDetailResponse(session=metadata)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "get session"))


@app.delete(
    "/sessions/{session_id}",
    response_model=SessionClearResponse,
    dependencies=[Depends(require_api_key)],
)
async def clear_session(session_id: str) -> SessionClearResponse:
    """Clear conversation history for a session."""
    if not settings.memory_enabled:
        raise HTTPException(status_code=404, detail="Memory is disabled")

    try:
        memory_manager = get_memory_manager()
        await memory_manager.clear_session(session_id)
        return SessionClearResponse(status="cleared", session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "clear session"))


@app.get(
    "/memory/stats",
    response_model=MemoryStats,
    dependencies=[Depends(require_api_key)],
)
async def memory_stats() -> MemoryStats:
    """Get memory system statistics."""
    try:
        memory_manager = get_memory_manager()
        stats = await memory_manager.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "memory stats"))


# Mount static files at the end after all routes are defined
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
