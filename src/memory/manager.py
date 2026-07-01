"""Memory manager for orchestrating conversation history."""

import logging
from functools import lru_cache

from pydantic_ai.messages import ModelMessage

from src.config import get_settings
from src.memory.models import MemoryStats, SessionMetadata
from src.memory.storage import InMemoryStorage, MemoryStorage

logger = logging.getLogger(__name__)


class MemoryManager:
    """Orchestrates memory storage and retrieval for conversation history."""

    def __init__(self, storage: MemoryStorage) -> None:
        """Initialize memory manager.

        Args:
            storage: Storage backend to use
        """
        self.storage = storage
        self.settings = get_settings()
        logger.info(f"Initialized MemoryManager with {type(storage).__name__}")

    async def get_history(
        self, session_id: str | None = None, user_id: str | None = None
    ) -> list[ModelMessage]:
        """Load conversation history for a session.

        Args:
            session_id: Explicit session identifier
            user_id: User identifier (used for auto-session if session_id is None)

        Returns:
            List of messages ordered from oldest to newest
        """
        if not self.settings.memory_enabled:
            logger.debug("Memory disabled, returning empty history")
            return []

        # Auto-generate session_id from user_id if not provided
        if session_id is None and user_id is not None and self.settings.memory_auto_session:
            session_id = f"user:{user_id}"
            logger.debug(f"Auto-generated session_id: {session_id}")

        if session_id is None:
            logger.debug("No session_id or user_id provided, returning empty history")
            return []

        # Retrieve messages with limit
        messages = await self.storage.get_messages(
            session_id, limit=self.settings.memory_max_messages
        )

        logger.info(f"Loaded {len(messages)} messages for session {session_id}")
        return messages

    async def save_turn(
        self,
        session_id: str | None,
        new_messages: list[ModelMessage],
        user_id: str | None = None,
    ) -> None:
        """Save new messages after an agent run.

        Args:
            session_id: Explicit session identifier
            new_messages: New messages from the agent run
            user_id: User identifier (used for auto-session if session_id is None)
        """
        if not self.settings.memory_enabled:
            logger.debug("Memory disabled, skipping save")
            return

        if not new_messages:
            logger.debug("No new messages to save")
            return

        # Auto-generate session_id from user_id if not provided
        if session_id is None and user_id is not None and self.settings.memory_auto_session:
            session_id = f"user:{user_id}"
            logger.debug(f"Auto-generated session_id: {session_id}")

        if session_id is None:
            logger.debug("No session_id or user_id provided, skipping save")
            return

        # Persist the full turn exactly as Pydantic AI produced it. The ModelMessage
        # format is designed to be replayed via `message_history` on the next run,
        # tool calls and returns included. Do NOT strip tool messages: doing so
        # corrupts multi-turn reasoning and, with a structured output_type, can drop
        # the assistant's answer entirely (the final output is itself a tool call).
        await self.storage.append_messages(session_id, new_messages)

        # Apply context window limit if needed
        if self.settings.memory_max_messages:
            current_messages = await self.storage.get_messages(session_id)
            if len(current_messages) > self.settings.memory_max_messages:
                # Keep only the most recent N messages
                trimmed = current_messages[-self.settings.memory_max_messages :]
                await self.storage.save_messages(session_id, trimmed)
                logger.info(
                    "Trimmed session %s from %d to %d messages",
                    session_id,
                    len(current_messages),
                    len(trimmed),
                )

        logger.info(f"Saved {len(new_messages)} messages to session {session_id}")

    async def clear_session(self, session_id: str) -> None:
        """Delete conversation history for a session.

        Args:
            session_id: Session identifier to clear
        """
        if not self.settings.memory_enabled:
            logger.debug("Memory disabled, skipping clear")
            return

        await self.storage.clear_session(session_id)
        logger.info(f"Cleared session {session_id}")

    async def list_sessions(self) -> list[SessionMetadata]:
        """List all conversation sessions.

        Returns:
            List of session metadata ordered by updated_at descending
        """
        if not self.settings.memory_enabled:
            logger.debug("Memory disabled, returning empty list")
            return []

        sessions = await self.storage.list_sessions()
        logger.debug(f"Listed {len(sessions)} sessions")
        return sessions

    async def get_session_metadata(self, session_id: str) -> SessionMetadata | None:
        """Get metadata for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Session metadata or None if not found
        """
        if not self.settings.memory_enabled:
            logger.debug("Memory disabled, returning None")
            return None

        metadata = await self.storage.get_metadata(session_id)
        logger.debug(f"Retrieved metadata for session {session_id}: {metadata is not None}")
        return metadata

    async def get_stats(self) -> MemoryStats:
        """Get statistics about the memory system.

        Returns:
            Memory system statistics
        """
        total_sessions = 0
        total_messages = 0

        if self.settings.memory_enabled:
            sessions = await self.storage.list_sessions()
            total_sessions = len(sessions)
            total_messages = sum(s.message_count for s in sessions)

        return MemoryStats(
            enabled=self.settings.memory_enabled,
            storage_type=self.settings.memory_storage_type,
            total_sessions=total_sessions,
            total_messages=total_messages,
            max_messages=self.settings.memory_max_messages,
        )


@lru_cache
def get_memory_manager() -> MemoryManager:
    """Get or create the singleton memory manager instance.

    Returns:
        Initialized memory manager
    """
    # Only an in-memory backend ships today. To add file/redis persistence,
    # implement the MemoryStorage interface and select it here.
    return MemoryManager(InMemoryStorage())
