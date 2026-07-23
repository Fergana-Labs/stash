import hashlib
import secrets
import time
from uuid import UUID

import bcrypt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_pool

security = HTTPBearer(auto_error=False)

_LAST_SEEN_DEBOUNCE_SECONDS = 60
_LAST_SEEN_CACHE_SIZE = 4096
API_KEY_TYPES = {"password", "manual", "cli", "invite", "machine"}
API_KEY_ACCESS_LEVELS = {"read", "full"}

# Mutating routes a read-access key may still call: pushing its own session
# transcripts/events is part of the read-key contract for production agents,
# and /ask is read semantics. Matched on FastAPI route templates.
_READ_KEY_WRITE_ALLOWLIST = {
    ("POST", "/api/v1/me/transcripts"),
    ("POST", "/api/v1/me/sessions"),
    ("POST", "/api/v1/me/sessions/{session_row_id}/artifacts"),
    ("POST", "/api/v1/me/sessions/events"),
    ("POST", "/api/v1/me/sessions/events/batch"),
    ("POST", "/api/v1/me/ask"),
}


class _LastSeenCache:
    """Bounded LRU cache mapping user_id → monotonic timestamp of last DB write."""

    def __init__(self, maxsize: int) -> None:
        self._data: dict[str, float] = {}
        self._maxsize = maxsize

    def get(self, key: str) -> float:
        val = self._data.pop(key, 0.0)
        if val:
            self._data[key] = val
        return val

    def set(self, key: str, value: float) -> None:
        self._data.pop(key, None)
        self._data[key] = value
        if len(self._data) > self._maxsize:
            oldest = next(iter(self._data))
            del self._data[oldest]


_last_seen_written = _LastSeenCache(_LAST_SEEN_CACHE_SIZE)


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------


def generate_api_key() -> str:
    return "st_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def create_api_key(
    user_id, name: str = "default", key_type: str = "manual", access: str = "full"
) -> str:
    """Mint a new API key for the user and persist its hash. Returns the raw key."""
    if key_type not in API_KEY_TYPES:
        raise ValueError(f"unknown API key type: {key_type}")
    if access not in API_KEY_ACCESS_LEVELS:
        raise ValueError(f"unknown API key access level: {access}")

    pool = get_pool()
    api_key = generate_api_key()
    await pool.execute(
        "INSERT INTO user_api_keys (user_id, key_hash, name, key_type, access) "
        "VALUES ($1, $2, $3, $4, $5)",
        user_id,
        hash_api_key(api_key),
        name[:128],
        key_type,
        access,
    )
    return api_key


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def _get_user_from_api_key(token: str, *, managed_auth_enabled: bool) -> dict:
    key_hash = hash_api_key(token)
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT u.id, u.name, u.display_name, u.email, u.description, "
        "       u.created_at, u.last_seen, u.role, u.referral_source, u.use_case, "
        "       u.plan, u.plan_intent, "
        "       k.id AS key_id, k.key_type, k.access AS key_access "
        "FROM user_api_keys k JOIN users u ON u.id = k.user_id "
        "WHERE k.key_hash = $1 AND k.revoked_at IS NULL",
        key_hash,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    user = dict(row)
    if managed_auth_enabled and user["key_type"] not in ("cli", "manual", "machine"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is not allowed for managed auth",
        )

    uid = str(user["id"])
    now = time.monotonic()
    if now - _last_seen_written.get(uid) > _LAST_SEEN_DEBOUNCE_SECONDS:
        _last_seen_written.set(uid, now)
        await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", user["id"])
        await pool.execute(
            "UPDATE user_api_keys SET last_used_at = now() WHERE id = $1", user["key_id"]
        )
    return user


async def _get_user_from_jwt(token: str) -> dict:
    from .managed.auth0.jwt import validate_auth0_token

    claims = await validate_auth0_token(token)
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, email, description, created_at, last_seen, "
        "       role, referral_source, use_case, plan, plan_intent "
        "FROM users WHERE auth0_sub = $1",
        claims["sub"],
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")

    user = dict(row)
    user["key_id"] = None
    user["key_access"] = "full"
    uid = str(user["id"])
    now = time.monotonic()
    if now - _last_seen_written.get(uid) > _LAST_SEEN_DEBOUNCE_SECONDS:
        _last_seen_written.set(uid, now)
        await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", user["id"])
    return user


async def authenticate_token(token: str) -> dict:
    """Resolve a raw bearer token (st_ API key or Auth0 JWT) to a user.

    For surfaces that can't carry an Authorization header, e.g. browser
    WebSockets passing the token as a query parameter."""
    from .config import settings

    # mc_ is the pre-rename (moltchat) prefix. Keys are stored hashed and the
    # raw values live with users, so issued mc_ keys can never be rewritten —
    # both prefixes stay valid for as long as those keys exist.
    if token.startswith(("st_", "mc_")):
        return await _get_user_from_api_key(token, managed_auth_enabled=settings.AUTH0_ENABLED)

    if settings.AUTH0_ENABLED:
        return await _get_user_from_jwt(token)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def _enforce_key_access(user: dict, request: Request) -> None:
    """Reject mutating requests from read-access keys.

    Matches on the resolved FastAPI route template (dependencies run after
    routing), so path params never need parsing. No matched route → deny.
    """
    if user["key_access"] == "full":
        return
    if request.method in ("GET", "HEAD"):
        return
    route = request.scope.get("route")
    if route is not None and (request.method, route.path) in _READ_KEY_WRITE_ALLOWLIST:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This API key is read-only (reads + transcript upload); "
        "this operation requires a full-access key",
    )


def _set_request_via(request: Request, user: dict | None) -> None:
    """Tag the request's caller surface for audit rows: 'ask' for the
    server-side VFS's nested reads (it marks them itself), 'cli' for API-key
    callers, 'web' for browser JWTs and anonymous reads. Analytics-grade only —
    the X-Stash-Via header is spoofable and must never gate authorization."""
    from .services.security_audit_service import request_via

    if request.headers.get("x-stash-via") == "ask":
        request_via.set("ask")
    elif user is not None and user.get("key_type"):
        request_via.set("cli")
    else:
        request_via.set("web")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    user = await authenticate_token(credentials.credentials)
    _enforce_key_access(user, request)
    _set_request_via(request, user)
    return user


async def get_scope(
    current_user: dict = Depends(get_current_user),
    x_stash_scope: str | None = Header(default=None),
) -> UUID:
    """The effective content scope for this request.

    The frontend's scope switcher sends `X-Stash-Scope: <scope_user_id>` when
    the user is working in a workspace; content routes own/list/create under
    that scope instead of the caller's personal one. Absent header → personal
    scope. A header naming a workspace the caller isn't a member of is a hard
    403 — never a silent fallback to personal.
    """
    if x_stash_scope is None:
        return current_user["id"]
    try:
        scope_user_id = UUID(x_stash_scope)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Stash-Scope must be a UUID")
    if scope_user_id == current_user["id"]:
        return scope_user_id

    from .services import permission_service

    if not await permission_service.is_workspace_member(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of that workspace")
    return scope_user_id


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
) -> dict | None:
    if credentials is None:
        _set_request_via(request, None)
        return None
    try:
        return await get_current_user(request, credentials)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise
