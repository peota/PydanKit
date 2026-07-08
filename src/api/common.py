"""Shared helpers, constants, and cross-route schemas for the API package.

Kept dependency-light (no imports from route modules) so any route can import it
without risking a circular import through ``src.api``.
"""

import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from pydantic import BaseModel

from src.config import get_settings

# api.py used to live in src/; this module is one level deeper (src/api/), so the
# static dir is two parents up + /static -> src/static.
STATIC_DIR = Path(__file__).parent.parent / "static"

try:
    APP_VERSION = _pkg_version("PydanKit")
except PackageNotFoundError:
    APP_VERSION = "0.0.0+dev"

logger = logging.getLogger("src.api")


def sanitize_error(e: Exception, context: str = "request") -> str:
    """Log error details internally and return a safe message for clients.

    Reads settings at call time (not import) so a reloaded app / cleared cache picks
    up the current DEBUG value.
    """
    logger.error(f"Error during {context}: {type(e).__name__}: {e}")
    if get_settings().debug:
        return f"{type(e).__name__}: {e}"
    return "An internal error occurred. Please try again later."


class SessionClearResponse(BaseModel):
    """Response body for endpoints that clear/revoke by id (sessions and keys)."""

    status: str
    session_id: str
