import base64
import hashlib
import hmac
import json
import secrets
import time

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_pool

security = HTTPBearer(auto_error=False)

_LAST_SEEN_DEBOUNCE_SECONDS = 60
_LAST_SEEN_CACHE_SIZE = 4096
API_KEY_TYPES = {"password", "manual", "cli", "invite"}


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
    return "mc_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def create_api_key(user_id, name: str = "default", key_type: str = "manual") -> str:
    """Mint a new API key for the user and persist its hash. Returns the raw key."""
    if key_type not in API_KEY_TYPES:
        raise ValueError(f"unknown API key type: {key_type}")

    pool = get_pool()
    api_key = generate_api_key()
    await pool.execute(
        "INSERT INTO user_api_keys (user_id, key_hash, name, key_type) " "VALUES ($1, $2, $3, $4)",
        user_id,
        hash_api_key(api_key),
        name[:128],
        key_type,
    )
    return api_key


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------------------------------------------------------------------------
# Dashboard tokens — short-lived, read-only, stateless (HMAC-signed)
# ---------------------------------------------------------------------------
# A stash-hosted dashboard runs in a sandboxed iframe that can't carry the
# owner's session cookie or a long-lived secret. At render time we mint one of
# these for the viewer and inject it; the dashboard reads the owner's data with
# it until it expires. Stateless so there's no row to write per page load.

DASHBOARD_TOKEN_PREFIX = "dt_"
DASHBOARD_TOKEN_DEFAULT_TTL = 900  # 15 minutes


def _dashboard_secret() -> bytes:
    from .config import settings

    if not settings.DASHBOARD_TOKEN_SECRET:
        raise HTTPException(status_code=503, detail="Dashboard tokens are not enabled")
    return settings.DASHBOARD_TOKEN_SECRET.encode()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def mint_dashboard_token(
    user_id, workspace_id, ttl_seconds: int = DASHBOARD_TOKEN_DEFAULT_TTL
) -> tuple[str, int]:
    """Sign a read-only token scoped to one user + workspace. Returns (token, exp_epoch)."""
    exp = int(time.time()) + ttl_seconds
    payload = {"uid": str(user_id), "ws": str(workspace_id), "exp": exp}
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url_encode(hmac.new(_dashboard_secret(), body.encode(), hashlib.sha256).digest())
    return f"{DASHBOARD_TOKEN_PREFIX}{body}.{sig}", exp


async def _get_user_from_dashboard_token(token: str) -> dict:
    raw = token[len(DASHBOARD_TOKEN_PREFIX) :]
    body, _, sig = raw.partition(".")
    expected = _b64url_encode(hmac.new(_dashboard_secret(), body.encode(), hashlib.sha256).digest())
    if not sig or not hmac.compare_digest(sig, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid dashboard token"
        )

    payload = json.loads(_b64url_decode(body))
    if payload["exp"] < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Dashboard token expired"
        )

    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, email, description, created_at, last_seen, "
        "       role, referral_source, use_case "
        "FROM users WHERE id = $1",
        payload["uid"],
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")

    user = dict(row)
    user["key_id"] = None
    user["read_only"] = True
    user["dashboard_workspace_id"] = payload["ws"]
    return user


# ---------------------------------------------------------------------------
# Publishable (anon) keys — workspace-scoped, browser-safe
# ---------------------------------------------------------------------------
# A `pk_` key identifies an app/workspace and is safe to embed in browser JS.
# It grants nothing on its own; `shares` rows (principal_type='api_key') decide
# which tables it can read or write (read-only unless an explicit write policy).

PUBLISHABLE_KEY_PREFIX = "pk_"


def generate_publishable_key() -> str:
    return PUBLISHABLE_KEY_PREFIX + secrets.token_urlsafe(32)


async def create_publishable_key(workspace_id, created_by, name: str = "default") -> str:
    """Mint a publishable key for the workspace and persist its hash. Returns the raw key."""
    pool = get_pool()
    key = generate_publishable_key()
    await pool.execute(
        "INSERT INTO publishable_keys (workspace_id, key_hash, name, created_by) "
        "VALUES ($1, $2, $3, $4)",
        workspace_id,
        hash_api_key(key),
        name[:128],
        created_by,
    )
    return key


async def resolve_publishable_key(token: str) -> dict:
    """Resolve a `pk_` token to {key_id, workspace_id, created_by}. 401 if unknown/revoked.

    `created_by` (the key's owner) is who anon writes are attributed to.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, created_by FROM publishable_keys "
        "WHERE key_hash = $1 AND revoked_at IS NULL",
        hash_api_key(token),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid publishable key"
        )

    kid = str(row["id"])
    now = time.monotonic()
    if now - _last_seen_written.get(kid) > _LAST_SEEN_DEBOUNCE_SECONDS:
        _last_seen_written.set(kid, now)
        await pool.execute(
            "UPDATE publishable_keys SET last_used_at = now() WHERE id = $1", row["id"]
        )
    return {
        "key_id": row["id"],
        "workspace_id": row["workspace_id"],
        "created_by": row["created_by"],
    }


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def _get_user_from_api_key(token: str, *, managed_auth_enabled: bool) -> dict:
    key_hash = hash_api_key(token)
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT u.id, u.name, u.display_name, u.email, u.description, "
        "       u.created_at, u.last_seen, u.role, u.referral_source, u.use_case, "
        "       k.id AS key_id, k.key_type "
        "FROM user_api_keys k JOIN users u ON u.id = k.user_id "
        "WHERE k.key_hash = $1 AND k.revoked_at IS NULL",
        key_hash,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    user = dict(row)
    if managed_auth_enabled and user["key_type"] != "cli":
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
        "       role, referral_source, use_case "
        "FROM users WHERE auth0_sub = $1",
        claims["sub"],
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")

    user = dict(row)
    user["key_id"] = None
    uid = str(user["id"])
    now = time.monotonic()
    if now - _last_seen_written.get(uid) > _LAST_SEEN_DEBOUNCE_SECONDS:
        _last_seen_written.set(uid, now)
        await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", user["id"])
    return user


async def resolve_user_token(token: str) -> dict:
    """Resolve a bearer token (mc_ key, dashboard token, or Auth0 JWT) to a user."""
    from .config import settings

    if token.startswith("mc_"):
        return await _get_user_from_api_key(token, managed_auth_enabled=settings.AUTH0_ENABLED)

    if token.startswith(DASHBOARD_TOKEN_PREFIX):
        return await _get_user_from_dashboard_token(token)

    if settings.AUTH0_ENABLED:
        return await _get_user_from_jwt(token)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    return await resolve_user_token(credentials.credentials)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
) -> dict | None:
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise
