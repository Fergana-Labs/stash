import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import create_api_key, get_current_user, hash_api_key
from ..config import settings
from ..database import get_pool
from ..middleware import limiter
from ..models import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyInfo,
    LoginRequest,
    RedeemInviteRequest,
    RedeemInviteResponse,
    UserProfile,
    UserRegisterRequest,
    UserRegisterResponse,
    UserUpdateRequest,
)
from ..services import invite_token_service, user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])

_CLI_AUTH_TTL_INTERVAL = user_service.CLI_AUTH_TTL_INTERVAL


def _require_password_auth() -> None:
    if settings.AUTH0_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password auth is disabled; use Auth0",
        )


def _require_manual_api_key_creation_enabled() -> None:
    if settings.AUTH0_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manual API key creation is disabled; use CLI sign-in",
        )


@router.post("/register", response_model=UserRegisterResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, req: UserRegisterRequest):
    _require_password_auth()
    try:
        user, api_key = await user_service.register_user(
            name=req.name,
            display_name=req.display_name,
            description=req.description,
            password=req.password,
            email=req.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return UserRegisterResponse(
        id=user["id"],
        name=user["name"],
        display_name=user["display_name"],
        api_key=api_key,
    )


@router.post("/login", response_model=UserRegisterResponse)
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest):
    _require_password_auth()
    try:
        user, api_key = await user_service.authenticate_by_password(
            name=req.name, password=req.password
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return UserRegisterResponse(
        id=user["id"],
        name=user["name"],
        display_name=user["display_name"],
        api_key=api_key,
    )


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserProfile(**current_user)


@router.post("/logout", status_code=204)
async def logout(current_user: dict = Depends(get_current_user)):
    """Revoke the API key that authenticated this request. The caller must
    also drop the key client-side — this just ensures the key can't be reused
    if it was captured elsewhere."""
    key_id = current_user.get("key_id")
    if not key_id:
        return None

    from ..database import get_pool

    pool = get_pool()
    await pool.execute(
        "UPDATE user_api_keys SET revoked_at = now() " "WHERE id = $1 AND revoked_at IS NULL",
        key_id,
    )
    return None


@router.patch("/me", response_model=UserProfile)
async def update_me(req: UserUpdateRequest, current_user: dict = Depends(get_current_user)):
    try:
        updated = await user_service.update_user(
            user_id=current_user["id"],
            display_name=req.display_name,
            description=req.description,
            password=req.password,
            current_password=req.current_password,
            current_key_id=current_user.get("key_id"),
            role=req.role,
            referral_source=req.referral_source,
            use_case=req.use_case,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return UserProfile(**updated)


# ---------------------------------------------------------------------------
# API keys — list and revoke
# ---------------------------------------------------------------------------


@router.get("/me/keys", response_model=list[ApiKeyInfo])
async def list_my_keys(current_user: dict = Depends(get_current_user)):
    from ..database import get_pool

    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, created_at, last_used_at "
        "FROM user_api_keys "
        "WHERE user_id = $1 AND revoked_at IS NULL "
        "ORDER BY created_at DESC",
        current_user["id"],
    )
    return [ApiKeyInfo(**dict(r)) for r in rows]


@router.post("/me/keys", response_model=ApiKeyCreateResponse, status_code=201)
@limiter.limit("10/minute")
async def create_my_key(
    request: Request,
    req: ApiKeyCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Mint a new API key for the current user. The raw key is returned once
    and never shown again; only its hash is stored."""
    _require_manual_api_key_creation_enabled()
    from ..database import get_pool

    api_key = await create_api_key(current_user["id"], name=req.name)
    pool = get_pool()
    from ..auth import hash_api_key

    row = await pool.fetchrow(
        "SELECT id, name, created_at FROM user_api_keys WHERE key_hash = $1",
        hash_api_key(api_key),
    )
    return ApiKeyCreateResponse(
        id=row["id"],
        name=row["name"],
        api_key=api_key,
        created_at=row["created_at"],
    )


@router.delete("/me/keys/{key_id}", status_code=204)
async def revoke_my_key(key_id: str, current_user: dict = Depends(get_current_user)):
    from ..database import get_pool

    pool = get_pool()
    result = await pool.execute(
        "UPDATE user_api_keys SET revoked_at = now() "
        "WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL",
        key_id,
        current_user["id"],
    )
    if not result.endswith(" 1"):
        raise HTTPException(status_code=404, detail="Key not found")
    return None


# ---------------------------------------------------------------------------
# CLI browser-based auth flow
# ---------------------------------------------------------------------------


@router.post("/cli-auth/sessions")
@limiter.limit("10/minute")
async def create_cli_auth_session(request: Request):
    """Create a CLI auth session. Returns a session_id the CLI uses to poll.

    Optional body `{"device_name": "..."}` names the key that'll be minted,
    so users can tell devices apart in `stash keys list`.
    """
    pool = get_pool()
    session_id = secrets.token_urlsafe(32)
    device_name = ""
    try:
        body = await request.json()
        device_name = str(body.get("device_name") or "")[:128]
    except Exception:
        pass
    await user_service.cleanup_expired_cli_auth_sessions()
    await pool.execute(
        "INSERT INTO cli_auth_sessions (session_id, device_name) VALUES ($1, $2)",
        session_id,
        device_name,
    )
    return {"session_id": session_id, "device_name": device_name}


@router.get("/cli-auth/sessions/{session_id}")
@limiter.limit("60/minute")
async def poll_cli_auth_session(request: Request, session_id: str):
    """Poll for CLI auth result. Returns pending or complete with api_key."""
    pool = get_pool()
    await user_service.cleanup_expired_cli_auth_sessions()
    # DELETE ... RETURNING makes the claim atomic: a session row is consumed
    # exactly once, either here (key delivered) or by the expiry cleanup (key
    # revoked) — never both, so a delivered key can't be revoked at the TTL
    # boundary by a concurrent cleanup.
    claimed = await pool.fetchrow(
        "DELETE FROM cli_auth_sessions "
        "WHERE session_id = $1 AND api_key IS NOT NULL "
        f"AND created_at > now() - interval '{_CLI_AUTH_TTL_INTERVAL}' "
        "RETURNING api_key, username",
        session_id,
    )
    if claimed:
        return {
            "status": "complete",
            "api_key": claimed["api_key"],
            "username": claimed["username"],
        }
    pending = await pool.fetchval(
        "SELECT 1 FROM cli_auth_sessions "
        f"WHERE session_id = $1 AND created_at > now() - interval '{_CLI_AUTH_TTL_INTERVAL}'",
        session_id,
    )
    if not pending:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return {"status": "pending"}


@router.post("/cli-auth/redeem-invite", response_model=RedeemInviteResponse)
@limiter.limit("10/minute")
async def redeem_invite_unauthenticated(request: Request, req: RedeemInviteRequest):
    """Redeem a magic-link invite token with no prior auth.

    Creates a brand-new user and joins them to the token's workspace. This is
    the path used by `stash connect --invite` for people who don't yet have a
    stash account.
    """
    result = await invite_token_service.redeem_as_new_user(
        raw_token=req.token,
        display_name=req.display_name,
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Invite token is invalid, expired, or exhausted",
        )
    return RedeemInviteResponse(**result)


@router.post("/cli-auth/sessions/{session_id}/approve")
@limiter.limit("10/minute")
async def approve_cli_auth_session(
    request: Request,
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Approve a CLI session with a freshly-minted key for the current user.

    The browser must be authenticated — we don't trust an `api_key` from the
    request body, because that would let any logged-in tab hand the CLI the
    browser's own session key. Instead we mint a new named key scoped to this
    device, so each CLI install has its own revocable identity.
    """
    pool = get_pool()
    await user_service.cleanup_expired_cli_auth_sessions()
    row = await pool.fetchrow(
        "SELECT device_name, api_key FROM cli_auth_sessions "
        f"WHERE session_id = $1 AND created_at > now() - interval '{_CLI_AUTH_TTL_INTERVAL}'",
        session_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    # Approve exactly once. A replayed approve must not mint a second key: the
    # first key's hash would stay active while its plaintext is overwritten,
    # leaving an orphan that the session-based cleanup can never revoke.
    if row["api_key"] is not None:
        return {"status": "approved"}

    device_name = row["device_name"] or "CLI"
    api_key = await create_api_key(current_user["id"], name=f"CLI ({device_name})")
    result = await pool.execute(
        "UPDATE cli_auth_sessions SET api_key = $1, username = $2 "
        "WHERE session_id = $3 AND api_key IS NULL",
        api_key,
        current_user["name"],
        session_id,
    )
    if result != "UPDATE 1":
        # Lost a concurrent approve race; revoke the key we just minted so it
        # cannot linger unreferenced.
        await pool.execute(
            "UPDATE user_api_keys SET revoked_at = now() "
            "WHERE key_hash = $1 AND revoked_at IS NULL",
            hash_api_key(api_key),
        )
    return {"status": "approved"}
