"""Pydantic models for memory system."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionMetadata(BaseModel):
    """Metadata about a conversation session."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "user:alice",
                "created_at": "2025-01-21T10:30:00",
                "updated_at": "2025-01-21T10:35:00",
                "message_count": 8,
                "user_id": "alice",
                "tags": {"source": "api"},
            }
        }
    )

    session_id: str = Field(..., description="Unique session identifier")
    created_at: datetime = Field(
        default_factory=datetime.now, description="Session creation timestamp"
    )
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    message_count: int = Field(default=0, description="Number of messages in session")
    user_id: str | None = Field(default=None, description="Associated user ID")
    tags: dict[str, str] = Field(default_factory=dict, description="Additional metadata tags")


class MemoryStats(BaseModel):
    """Statistics about the memory system."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "storage_type": "memory",
                "total_sessions": 3,
                "total_messages": 42,
                "max_messages": 100,
            }
        }
    )

    enabled: bool = Field(..., description="Whether memory is enabled")
    storage_type: Literal["memory", "sqlite"] = Field(..., description="Storage backend type")
    total_sessions: int = Field(default=0, description="Total number of sessions")
    total_messages: int = Field(
        default=0, description="Total number of messages across all sessions"
    )
    max_messages: int | None = Field(default=None, description="Maximum messages per session")
