import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import get_current_user
from ..config import settings
from ..middleware import limiter
from ..models import (
    ApiKeyInfo,
    LoginRequest,
    RedeemInviteRequest,
    RedeemInviteResponse,
    UserProfile,
    UserRegisterRequest,
    UserRegisterResponse,
    UserSearchResult,
    UserUpdateRequest,
)
from ..services import invite_token_service, user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# ---------------------------------------------------------------------------
# CLI auth sessions — in-memory, short-lived (10 min TTL)
# ---------------------------------------------------------------------------

_CLI_AUTH_TTL = 600  # seconds
_cli_sessions: dict[str, dict] = {}  # session_id → {created_at, api_key?, username?}


def _prune_cli_sessions() -> None:
    cutoff = time.time() - _CLI_AUTH_TTL
    expired = [k for k, v in _cli_sessions.items() if v["created_at"] < cutoff]
    for k in expired:
        del _cli_sessions[k]


def _require_password_auth() -> None:
    if settings.AUTH0_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password auth is disabled; use Auth0",
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


@router.patch("/me", response_model=UserProfile)
async def update_me(req: UserUpdateRequest, current_user: dict = Depends(get_current_user)):
    updated = await user_service.update_user(
        user_id=current_user["id"],
        display_name=req.display_name,
        description=req.description,
        password=req.password,
    )
    return UserProfile(**updated)


@router.get("/search", response_model=list[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=1, max_length=64),
    current_user: dict = Depends(get_current_user),
):
    """Search for users by name or display name."""
    from ..database import get_pool

    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, display_name FROM users "
        "WHERE (name ILIKE $1 OR display_name ILIKE $1) AND id != $2 "
        "LIMIT 20",
        f"%{q}%",
        current_user["id"],
    )
    return [UserSearchResult(**dict(r)) for r in rows]


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
    _prune_cli_sessions()
    session_id = secrets.token_urlsafe(32)
    device_name = ""
    try:
        body = await request.json()
        device_name = str(body.get("device_name") or "")[:128]
    except Exception:
        pass
    _cli_sessions[session_id] = {"created_at": time.time(), "device_name": device_name}
    return {"session_id": session_id, "device_name": device_name}


@router.get("/cli-auth/sessions/{session_id}")
@limiter.limit("60/minute")
async def poll_cli_auth_session(request: Request, session_id: str):
    """Poll for CLI auth result. Returns pending or complete with api_key."""
    _prune_cli_sessions()
    session = _cli_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if "api_key" in session:
        del _cli_sessions[session_id]
        return {
            "status": "complete",
            "api_key": session["api_key"],
            "username": session["username"],
        }
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
async def approve_cli_auth_session(request: Request, session_id: str):
    """Called by the frontend after login to approve the CLI session."""
    body = await request.json()
    api_key = body.get("api_key")
    username = body.get("username")
    if not api_key or not username:
        raise HTTPException(status_code=400, detail="api_key and username required")
    _prune_cli_sessions()
    session = _cli_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    session["api_key"] = api_key
    session["username"] = username
    return {"status": "approved"}
