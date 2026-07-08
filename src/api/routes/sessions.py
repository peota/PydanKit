"""Session routes: list/inspect/clear conversation threads and memory stats.

Every data route scopes to the caller when auth is on: the same 404 is returned for
"absent" and "not yours" so ownership isn't leaked.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from src.api.common import SessionClearResponse, sanitize_error
from src.auth.db import User
from src.auth.dependencies import get_current_user
from src.config import get_settings
from src.memory.manager import get_memory_manager
from src.memory.models import MemoryStats, SessionMetadata

router = APIRouter(tags=["Sessions"])


class SessionListResponse(BaseModel):
    """Response body for sessions list endpoint."""

    sessions: list[SessionMetadata]


class SessionDetailResponse(BaseModel):
    """Response body for session detail endpoint."""

    session: SessionMetadata


class SessionMessage(BaseModel):
    """One rendered turn for display (a user prompt or the assistant's text)."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class SessionMessagesResponse(BaseModel):
    """A session's messages flattened to displayable text for the dashboard."""

    session_id: str
    messages: list[SessionMessage]


def _owns_session(user: User | None, metadata: SessionMetadata) -> bool:
    """A data route is in-bounds if auth is off, or the session is the caller's."""
    return user is None or metadata.user_id == user.username


def _render_messages(history: list[ModelMessage]) -> list[SessionMessage]:
    """Flatten stored ModelMessages to {role, content}, keeping only text parts."""
    rendered: list[SessionMessage] = []
    for msg in history:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    rendered.append(SessionMessage(role="user", content=part.content))
        elif isinstance(msg, ModelResponse):
            text = "".join(p.content for p in msg.parts if isinstance(p, TextPart))
            if text:
                rendered.append(SessionMessage(role="assistant", content=text))
    return rendered


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user: User | None = Depends(get_current_user),
) -> SessionListResponse:
    """List conversation sessions (scoped to the caller when authenticated)."""
    if not get_settings().memory_enabled:
        return SessionListResponse(sessions=[])

    try:
        memory_manager = get_memory_manager()
        sessions = await memory_manager.list_sessions()
        if user is not None:
            sessions = [s for s in sessions if s.user_id == user.username]
        return SessionListResponse(sessions=sessions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "list sessions"))


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str, user: User | None = Depends(get_current_user)
) -> SessionDetailResponse:
    """Get details for a specific session (only the caller's when authenticated)."""
    if not get_settings().memory_enabled:
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


@router.delete("/sessions/{session_id}", response_model=SessionClearResponse)
async def clear_session(
    session_id: str, user: User | None = Depends(get_current_user)
) -> SessionClearResponse:
    """Clear conversation history for a session (only the caller's when authenticated)."""
    if not get_settings().memory_enabled:
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


@router.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_session_messages(
    session_id: str, user: User | None = Depends(get_current_user)
) -> SessionMessagesResponse:
    """Return a session's messages as displayable text (only the caller's when authed)."""
    if not get_settings().memory_enabled:
        raise HTTPException(status_code=404, detail="Memory is disabled")
    try:
        memory_manager = get_memory_manager()
        metadata = await memory_manager.get_session_metadata(session_id)
        if metadata is None or not _owns_session(user, metadata):
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        history = await memory_manager.get_history(session_id=session_id)
        return SessionMessagesResponse(session_id=session_id, messages=_render_messages(history))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "get session messages"))


@router.get("/memory/stats", response_model=MemoryStats)
async def memory_stats(user: User | None = Depends(get_current_user)) -> MemoryStats:
    """Get memory system statistics (scoped to the caller when authenticated)."""
    settings = get_settings()
    try:
        memory_manager = get_memory_manager()
        if user is None:
            return await memory_manager.get_stats()
        # Scope counts to the caller's own sessions.
        own = [s for s in await memory_manager.list_sessions() if s.user_id == user.username]
        return MemoryStats(
            enabled=settings.memory_enabled,
            storage_type=settings.effective_memory_backend,
            total_sessions=len(own),
            total_messages=sum(s.message_count for s in own),
            max_messages=settings.memory_max_messages,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, "memory stats"))
