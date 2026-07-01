"""Context window management utilities for memory system."""

import logging

from pydantic_ai.messages import ModelMessage

logger = logging.getLogger(__name__)


def truncate_by_message_count(
    messages: list[ModelMessage], max_messages: int
) -> list[ModelMessage]:
    """Truncate message history to keep only the N most recent messages.

    Args:
        messages: List of messages ordered from oldest to newest
        max_messages: Maximum number of messages to keep

    Returns:
        Truncated list of messages
    """
    if len(messages) <= max_messages:
        return messages

    truncated = messages[-max_messages:]
    logger.debug(f"Truncated messages from {len(messages)} to {len(truncated)}")
    return truncated
