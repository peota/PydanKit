"""Storage abstraction for memory system."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic_ai.messages import ModelMessage

from src.memory.models import SessionMetadata

logger = logging.getLogger(__name__)


class MemoryStorage(ABC):
    """Abstract interface for memory storage backends."""

    @abstractmethod
    async def get_messages(self, session_id: str, limit: int | None = None) -> list[ModelMessage]:
        """Retrieve messages for a session.

        Args:
            session_id: Unique session identifier
            limit: Maximum number of messages to return (most recent first)

        Returns:
            List of messages ordered from oldest to newest
        """
        pass

    @abstractmethod
    async def save_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        """Replace all messages for a session.

        Args:
            session_id: Unique session identifier
            messages: Complete list of messages to save
        """
        pass

    @abstractmethod
    async def append_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        """Append new messages to a session.

        Args:
            session_id: Unique session identifier
            messages: New messages to append
        """
        pass

    @abstractmethod
    async def clear_session(self, session_id: str) -> None:
        """Delete all messages for a session.

        Args:
            session_id: Unique session identifier
        """
        pass

    @abstractmethod
    async def list_sessions(self) -> list[SessionMetadata]:
        """List all sessions.

        Returns:
            List of session metadata ordered by updated_at descending
        """
        pass

    @abstractmethod
    async def get_metadata(self, session_id: str) -> SessionMetadata | None:
        """Get metadata for a specific session.

        Args:
            session_id: Unique session identifier

        Returns:
            Session metadata or None if session doesn't exist
        """
        pass


class InMemoryStorage(MemoryStorage):
    """In-memory storage implementation using a dictionary."""

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        self._sessions: dict[str, list[ModelMessage]] = {}
        self._metadata: dict[str, SessionMetadata] = {}
        logger.debug("Initialized InMemoryStorage")

    async def get_messages(self, session_id: str, limit: int | None = None) -> list[ModelMessage]:
        """Retrieve messages for a session."""
        messages = self._sessions.get(session_id, [])

        if limit is not None and limit > 0:
            # Return the most recent N messages
            messages = messages[-limit:]

        logger.debug(f"Retrieved {len(messages)} messages for session {session_id}")
        return messages

    async def save_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        """Replace all messages for a session."""
        self._sessions[session_id] = list(messages)
        await self._update_metadata(session_id)
        logger.debug(f"Saved {len(messages)} messages for session {session_id}")

    async def append_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        """Append new messages to a session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = []

        self._sessions[session_id].extend(messages)
        await self._update_metadata(session_id)
        logger.debug(f"Appended {len(messages)} messages to session {session_id}")

    async def clear_session(self, session_id: str) -> None:
        """Delete all messages for a session."""
        self._sessions.pop(session_id, None)
        self._metadata.pop(session_id, None)
        logger.debug(f"Cleared session {session_id}")

    async def list_sessions(self) -> list[SessionMetadata]:
        """List all sessions."""
        sessions = list(self._metadata.values())
        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        logger.debug(f"Listed {len(sessions)} sessions")
        return sessions

    async def get_metadata(self, session_id: str) -> SessionMetadata | None:
        """Get metadata for a specific session."""
        metadata = self._metadata.get(session_id)
        logger.debug(f"Retrieved metadata for session {session_id}: {metadata is not None}")
        return metadata

    async def _update_metadata(self, session_id: str) -> None:
        """Update metadata for a session."""
        now = datetime.now()
        message_count = len(self._sessions.get(session_id, []))

        if session_id in self._metadata:
            # Update existing metadata
            self._metadata[session_id].updated_at = now
            self._metadata[session_id].message_count = message_count
        else:
            # Create new metadata
            # Try to extract user_id from session_id pattern "user:xyz"
            user_id = None
            if session_id.startswith("user:"):
                user_id = session_id.split(":", 1)[1]

            self._metadata[session_id] = SessionMetadata(
                session_id=session_id,
                created_at=now,
                updated_at=now,
                message_count=message_count,
                user_id=user_id,
            )
