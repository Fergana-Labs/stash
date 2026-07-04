import hashlib
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
        "INSERT INTO user_api_keys (user_id, key_hash, name, key_type) VALUES ($1, $2, $3, $4)",
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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    token: str = credentials.credentials
    from .config import settings

    if token.startswith("mc_"):
        return await _get_user_from_api_key(token, managed_auth_enabled=settings.AUTH0_ENABLED)

    if settings.AUTH0_ENABLED:
        return await _get_user_from_jwt(token)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


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
