"""Admin routes: service accounts & API keys.

All routes require an admin; ``require_admin`` returns 404 when auth is disabled
(no admin identity exists), so the whole surface is invisible in the open config.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.common import SessionClearResponse
from src.auth.db import InvalidUsernameError, User, UsernameTakenError
from src.auth.dependencies import get_auth_store, require_admin
from src.auth.tokens import hash_token

router = APIRouter(tags=["Admin"])


class CreateServiceAccountRequest(BaseModel):
    """Create a passwordless, non-admin service account."""

    username: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")


class AdminUserResponse(BaseModel):
    """A user as seen by the admin panel (never includes a password/secret)."""

    id: int
    username: str
    is_admin: bool
    disabled: bool
    is_service: bool
    created_at: float


class IssueKeyRequest(BaseModel):
    """Issue an API key for a service account; optional human label."""

    name: str | None = Field(default=None, max_length=128)


class IssuedKeyResponse(BaseModel):
    """Returned once when a key is minted — carries the plaintext key."""

    token_hash: str
    name: str | None
    key: str = Field(..., description="Plaintext key — shown once, store it now")


class AdminKeyResponse(BaseModel):
    """Key metadata for listing (never the plaintext value)."""

    token_hash: str
    name: str | None
    created_at: float
    expires_at: float | None


def _to_admin_user(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        disabled=user.disabled,
        is_service=user.is_service,
        created_at=user.created_at,
    )


async def _require_managed_user(user_id: int) -> User:
    """Load a user for admin ops, or 404. (Read-only routes may use any user.)"""
    user = await get_auth_store().get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    return user


async def _require_non_admin_user(user_id: int) -> User:
    """Load a user for admin MUTATIONS, rejecting admin accounts.

    Admin accounts are never managed from the UI: issuing an admin an API key would
    mint a non-expiring, admin-privileged credential that bypasses the cookie/CSRF
    path — the escalation this endpoint must not enable.
    """
    user = await _require_managed_user(user_id)
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Admin accounts cannot be managed from the UI")
    return user


@router.post("/admin/users", response_model=AdminUserResponse, status_code=201)
async def admin_create_service_account(
    body: CreateServiceAccountRequest, _admin: User = Depends(require_admin)
) -> AdminUserResponse:
    """Create a non-admin, passwordless service account (holds API keys, can't log in)."""
    store = get_auth_store()
    try:
        user = await store.create_service_account(body.username)
    except UsernameTakenError:
        raise HTTPException(status_code=409, detail=f"Username already exists: {body.username}")
    except InvalidUsernameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_admin_user(user)


@router.get("/admin/users", response_model=list[AdminUserResponse])
async def admin_list_users(_admin: User = Depends(require_admin)) -> list[AdminUserResponse]:
    """List all accounts (admins, humans, and service accounts)."""
    users = await get_auth_store().list_users()
    return [_to_admin_user(u) for u in users]


@router.post("/admin/users/{user_id}/keys", response_model=IssuedKeyResponse, status_code=201)
async def admin_issue_key(
    user_id: int, body: IssueKeyRequest, _admin: User = Depends(require_admin)
) -> IssuedKeyResponse:
    """Issue an API key for a non-admin account. Plaintext returned once, never stored."""
    user = await _require_non_admin_user(user_id)
    store = get_auth_store()
    key = await store.issue_token(user.id, "api_key", name=body.name)
    return IssuedKeyResponse(token_hash=hash_token(key), name=body.name, key=key)


@router.get("/admin/users/{user_id}/keys", response_model=list[AdminKeyResponse])
async def admin_list_keys(
    user_id: int, _admin: User = Depends(require_admin)
) -> list[AdminKeyResponse]:
    """List a user's active API keys (metadata only — the value is never re-shown)."""
    user = await _require_managed_user(user_id)
    tokens = await get_auth_store().list_tokens(user.id, kind="api_key")
    return [
        AdminKeyResponse(
            token_hash=t.token_hash, name=t.name, created_at=t.created_at, expires_at=t.expires_at
        )
        for t in tokens
    ]


@router.delete("/admin/keys/{token_hash}", response_model=SessionClearResponse)
async def admin_revoke_key(
    token_hash: str, _admin: User = Depends(require_admin)
) -> SessionClearResponse:
    """Revoke a key by its hash handle (rotation). 404 if it doesn't exist / already revoked."""
    revoked = await get_auth_store().revoke_token_by_hash(token_hash)
    if not revoked:
        raise HTTPException(status_code=404, detail="Key not found or already revoked")
    return SessionClearResponse(status="revoked", session_id=token_hash)


async def _set_disabled(user_id: int, disabled: bool) -> AdminUserResponse:
    """Toggle a non-admin account's disabled flag. Admin accounts aren't UI-managed.

    Disabling freezes the account and all its keys (auth resolution rejects a disabled
    owner); it does not revoke or delete keys. Enabling restores them unchanged.
    """
    user = await _require_non_admin_user(user_id)
    store = get_auth_store()
    await store.set_disabled(user.id, disabled)
    return _to_admin_user(await store.get_user_by_id(user.id))


@router.post("/admin/users/{user_id}/disable", response_model=AdminUserResponse)
async def admin_disable_user(
    user_id: int, _admin: User = Depends(require_admin)
) -> AdminUserResponse:
    """Disable a non-admin account (freezes it and its keys; reversible)."""
    return await _set_disabled(user_id, True)


@router.post("/admin/users/{user_id}/enable", response_model=AdminUserResponse)
async def admin_enable_user(
    user_id: int, _admin: User = Depends(require_admin)
) -> AdminUserResponse:
    """Re-enable a disabled non-admin account; its existing keys work again."""
    return await _set_disabled(user_id, False)
