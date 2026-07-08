"""FastAPI server for the agent (optional feature).

Install with: pip install -e ".[api]"
Run with: python -m src.main serve

This package assembles the app from per-concern route modules in ``routes/``. Route
handlers read settings at request time (via ``get_settings()``), so this module —
the only one ``importlib.reload(src.api)`` re-executes — is where app-construction
config (docs, CORS, lifespan) is resolved against the current environment.
"""

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
except ImportError:
    raise ImportError("FastAPI is not installed. Install it with: pip install -e '.[api]'")

import logging
from contextlib import asynccontextmanager

from src.api.common import APP_VERSION, STATIC_DIR, SessionClearResponse, sanitize_error
from src.api.routes import admin, auth, chat, sessions, system

# Re-exported so callers/tests importing from ``src.api`` keep working after the
# split (e.g. ``from src.api import ChatRequest, _deps_for``; ``api.get_auth_store``).
from src.api.routes.chat import ChatRequest, ChatResponse, _deps_for  # noqa: F401
from src.auth.dependencies import get_auth_store  # noqa: F401
from src.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def _lifespan(_app: "FastAPI"):
    """Seed the first admin from the environment on a shell-less deploy.

    Only runs when auth is on, ADMIN_USERNAME/ADMIN_PASSWORD are set, and no admin
    exists yet. Idempotent — a no-op once an admin is present.
    """
    if settings.auth_enabled and settings.admin_username and settings.admin_password:
        store = get_auth_store()
        if not await store.has_admin():
            try:
                await store.create_user(
                    settings.admin_username, settings.admin_password, is_admin=True
                )
                logger.info("Seeded initial admin '%s' from environment", settings.admin_username)
            except Exception as e:  # never block startup on a seed hiccup
                logger.warning("Admin env-seed skipped: %s", e)

    # Auth is durable (the DATABASE_URL engine) but the default memory backend is
    # process-local. Under multiple workers that's a silent inconsistency — warn.
    if (
        settings.auth_enabled
        and settings.memory_enabled
        and settings.effective_memory_backend == "memory"
    ):
        logger.warning(
            "Memory backend is 'memory' (process-local, lost on restart, not shared "
            "across workers) while auth is enabled. Set MEMORY_STORAGE_TYPE=sql for "
            "durable, worker-shared conversation history."
        )
    yield


# Hide interactive docs (Swagger/ReDoc/openapi.json) unless enabled — off in prod by
# default so the API surface (incl. /admin/*) isn't advertised. See docs_ui_enabled.
_docs_urls: dict = (
    {} if settings.docs_ui_enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}
)
# Group endpoints into sections in the /docs UI (defines their order + descriptions).
_OPENAPI_TAGS = [
    {"name": "System", "description": "Dashboard, health, and agent metadata."},
    {"name": "Auth", "description": "Login and logout (session cookie)."},
    {"name": "Chat", "description": "Send prompts to the agent."},
    {"name": "Sessions", "description": "Conversation sessions and memory."},
    {"name": "Admin", "description": "Service accounts and API keys (admin only)."},
]

# Configure CORS from settings (default is a localhost allowlist, not "*").
# Credentials are enabled so the session cookie works cross-origin from allowed
# origins. The spec forbids credentials + wildcard: Starlette would reflect the
# caller's Origin and set Allow-Credentials, letting any site ride the victim's
# cookie. Fail fast rather than trust a comment.
if "*" in settings.cors_origins:
    raise ValueError(
        "CORS_ORIGINS must not contain '*': credentials are enabled, so a wildcard "
        "origin is a credential-leak vector. Set explicit origins."
    )

app = FastAPI(
    title=f"{settings.agent_name} API",
    description=f"REST API for {settings.agent_name}",
    version=APP_VERSION,
    lifespan=_lifespan,
    openapi_tags=_OPENAPI_TAGS,
    **_docs_urls,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Requested-With"],
)


@app.middleware("http")
async def _no_cache_dashboard(request, call_next):
    """Serve the dashboard and its assets without caching.

    This is a dev/demo dashboard: edits to the HTML/JS should show up on reload,
    not be shadowed by the browser's heuristic cache.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# Order mirrors the OpenAPI tag order above. Static is mounted last, after all routes.
app.include_router(system.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(admin.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

__all__ = [
    "app",
    "ChatRequest",
    "ChatResponse",
    "_deps_for",
    "get_auth_store",
    "sanitize_error",
    "SessionClearResponse",
]
