"""Auth routes: password login (sets an HttpOnly session cookie) and logout."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.auth.dependencies import (
    SESSION_COOKIE,
    clear_session_cookie,
    get_auth_store,
    set_session_cookie,
)
from src.config import get_settings

router = APIRouter(tags=["Auth"])


class LoginRequest(BaseModel):
    """Request body for the login endpoint."""

    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    """Response body for a successful login."""

    username: str
    is_admin: bool


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response) -> LoginResponse:
    """Verify a password and set an HttpOnly session cookie.

    Only meaningful when AUTH_ENABLED is true. Applies a per-username brute-force
    lockout.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=400, detail="Authentication is disabled")

    store = get_auth_store()
    if await store.is_locked_out(
        body.username, settings.login_max_attempts, settings.login_lockout_seconds
    ):
        raise HTTPException(status_code=429, detail="Too many attempts; try again later")

    user = await store.verify_login(body.username, body.password)
    if user is None:
        await store.record_failure(body.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    await store.clear_failures(body.username)
    ttl = settings.session_ttl_days * 86400
    token = await store.issue_token(user.id, "session", name="dashboard", ttl_seconds=ttl)
    set_session_cookie(response, token, ttl)
    return LoginResponse(username=user.username, is_admin=user.is_admin)


@router.post("/auth/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Revoke the current session token and clear the cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await get_auth_store().revoke_token(token)
    clear_session_cookie(response)
    return {"status": "logged out"}
