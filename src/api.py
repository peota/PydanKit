"""FastAPI server for the agent (optional feature).

Install with: pip install -e ".[api]"
Run with: python -m src.main serve
"""

from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    raise ImportError(
        "FastAPI is not installed. Install it with: pip install -e '.[api]'"
    )

import logging

from pydantic import BaseModel, Field

from src.agent import get_agent_info, run_agent, run_agent_stream
from src.config import get_settings
from src.dependencies import AgentDeps
from src.models import AgentResponse

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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=False,  # Must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    content: str = Field(..., description="The agent's response")
    confidence: float | None = Field(default=None, description="Confidence score (0-1)")


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
    error: str | None = None


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
            error=sanitize_error(e, "info"),
        )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a prompt to the agent and get a response."""
    try:
        deps = AgentDeps(user_id=request.user_id)
        result: AgentResponse = await run_agent(request.prompt, deps)
        return ChatResponse(content=result.content, confidence=result.confidence)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "chat"))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Send a prompt to the agent and get a streaming response."""
    try:
        deps = AgentDeps(user_id=request.user_id)

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
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "chat stream"))


# Mount static files at the end after all routes are defined
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
