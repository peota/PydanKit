"""Context window management utilities for memory system."""

import logging

from pydantic_ai.messages import ModelMessage

logger = logging.getLogger(__name__)


def truncate_by_message_count(messages: list[ModelMessage], max_messages: int) -> list[ModelMessage]:
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


def truncate_by_token_count(messages: list[ModelMessage], max_tokens: int) -> list[ModelMessage]:
    """Truncate message history to fit within a token budget.

    This is a rough estimate based on character count (4 chars ≈ 1 token).
    For more accurate token counting, integrate with a tokenizer library.

    Args:
        messages: List of messages ordered from oldest to newest
        max_tokens: Maximum tokens allowed

    Returns:
        Truncated list of messages
    """
    if not messages:
        return messages

    # Rough estimate: 4 characters per token
    chars_per_token = 4
    max_chars = max_tokens * chars_per_token

    # Start from the most recent message and work backwards
    selected_messages = []
    total_chars = 0

    for message in reversed(messages):
        # Estimate message size (simplified - just count string representation)
        message_chars = len(str(message))

        if total_chars + message_chars > max_chars:
            # Would exceed budget, stop here
            break

        selected_messages.insert(0, message)
        total_chars += message_chars

    logger.debug(
        f"Truncated messages from {len(messages)} to {len(selected_messages)} "
        f"to fit ~{max_tokens} tokens ({total_chars} chars)"
    )
    return selected_messages


def estimate_token_count(messages: list[ModelMessage]) -> int:
    """Estimate the token count for a list of messages.

    This is a rough estimate based on character count (4 chars ≈ 1 token).

    Args:
        messages: List of messages

    Returns:
        Estimated token count
    """
    total_chars = sum(len(str(msg)) for msg in messages)
    estimated_tokens = total_chars // 4
    return estimated_tokens
