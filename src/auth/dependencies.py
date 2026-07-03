"""FastAPI auth dependencies: one resolver, two doors (ADR 0001, Phase 3).

``get_current_user`` accepts a credential from either an HttpOnly session cookie
(humans) or an ``Authorization: Bearer`` / ``X-API-Key`` header (programs), resolves
it through the shared token store, and returns the ``User``.

When ``AUTH_ENABLED`` is false the resolver returns ``None`` (the API is open) but
still honors the legacy single-secret ``API_KEY`` gate, preserving today's behavior
for deployments that haven't adopted per-user auth.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Request, Response

from src.auth.db import AuthStore, User
from src.config import get_settings

SESSION_COOKIE = "pk_session"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@lru_cache
def get_auth_store() -> AuthStore:
    """Singleton auth store over the configured SQLite database."""
    return AuthStore(get_settings().database_path)


def _extract_token(
    request: Request, authorization: str | None, x_api_key: str | None
) -> tuple[str | None, bool]:
    """Return (token, from_cookie). Cookie wins so browsers never fall back to a header."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie, True
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip(), False
    if x_api_key:
        return x_api_key, False
    return None, False


def set_session_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    """Attach the HttpOnly session cookie. JS can't read it, so XSS can't steal it."""
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


async def get_current_user(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> User | None:
    """Resolve the caller, or None when auth is disabled. Raises 401/403 otherwise."""
    settings = get_settings()

    if not settings.auth_enabled:
        # Legacy single-shared-secret gate, preserved for the auth-off deployment.
        if settings.api_key and x_api_key != settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        return None

    store = get_auth_store()
    token, from_cookie = _extract_token(request, authorization, x_api_key)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = await store.resolve_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials")

    # Light CSRF: a cross-site page can auto-send the cookie but can't set a custom
    # header without a CORS preflight we don't grant. Only guards unsafe methods.
    if from_cookie and request.method not in _SAFE_METHODS:
        if request.headers.get("x-requested-with") is None:
            raise HTTPException(status_code=403, detail="Missing CSRF header")

    # Sliding session: push expiry forward and refresh the cookie on activity.
    if from_cookie:
        ttl = settings.session_ttl_days * 86400
        await store.extend_token(token, ttl)
        set_session_cookie(response, token, ttl)

    return user


async def require_admin(user: User | None = Depends(get_current_user)) -> User:
    """Gate admin-only routes (ADR 0002).

    404 when auth is disabled (no admin identity exists, so the feature is
    unavailable). Otherwise the caller must be an authenticated admin: 401 for no
    credential (raised by get_current_user), 403 for a non-admin.
    """
    if not get_settings().auth_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    if user is None or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user
