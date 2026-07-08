"""Chat routes: one-shot and streaming (SSE) prompts to the agent."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent import run_agent, run_agent_stream
from src.api.common import sanitize_error
from src.auth.db import User
from src.auth.dependencies import get_current_user
from src.dependencies import AgentDeps

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    """Request body for chat endpoint.

    ``user_id`` is intentionally absent: when auth is enabled the caller's
    identity comes from their credential, never the request body. When auth is
    disabled, ``session_id`` provides conversation continuity as before.
    """

    prompt: str = Field(
        ..., min_length=1, max_length=10000, description="The prompt to send to the agent"
    )
    session_id: str | None = Field(
        default=None,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_-]*$",
        description="Conversation thread id. When authenticated it is namespaced under "
        "your account (user:<name>:<id>); omit for your default thread.",
    )
    memory_enabled: bool = Field(
        default=True,
        description="Enable memory for this request (default: true)",
    )


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    content: str = Field(..., description="The agent's response")


def _deps_for(user: User | None, request: ChatRequest) -> AgentDeps:
    """Build AgentDeps, scoping memory to the authenticated user when present.

    Authenticated: sessions are namespaced under the caller — ``user:<name>`` (the
    default thread) or ``user:<name>:<session_id>`` for a specific one. The client picks
    the thread but can never escape its own namespace.
    Anonymous (auth off): the request's session_id drives continuity as before.
    """
    if user is not None:
        base = f"user:{user.username}"
        # session_id is a colon-free thread id (validated on ChatRequest); prefixing it
        # keeps every thread owned by, and scoped to, this user.
        session_id = f"{base}:{request.session_id}" if request.session_id else base
        return AgentDeps(
            user_id=user.username,
            session_id=session_id,
            memory_enabled=request.memory_enabled,
        )
    return AgentDeps(
        user_id=None, session_id=request.session_id, memory_enabled=request.memory_enabled
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: User | None = Depends(get_current_user)) -> ChatResponse:
    """Send a prompt to the agent and get a response."""
    try:
        content = await run_agent(request.prompt, _deps_for(user, request))
        return ChatResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "chat"))


@router.post("/chat/stream")
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
                    # JSON-encode so a chunk containing newlines stays a single SSE
                    # `data:` line (a raw newline would split the frame and the client
                    # would drop the continuation). Client does JSON.parse to recover it.
                    yield f"data: {json.dumps(chunk)}\n\n"
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
