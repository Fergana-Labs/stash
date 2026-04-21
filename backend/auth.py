import hashlib
import secrets
import time

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_pool

security = HTTPBearer()

_LAST_SEEN_DEBOUNCE_SECONDS = 60
_LAST_SEEN_CACHE_SIZE = 4096


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


async def create_api_key(user_id, name: str = "default") -> str:
    """Mint a new API key for the user and persist its hash. Returns the raw key."""
    pool = get_pool()
    api_key = generate_api_key()
    await pool.execute(
        "INSERT INTO user_api_keys (user_id, key_hash, name) VALUES ($1, $2, $3)",
        user_id,
        hash_api_key(api_key),
        name[:128],
    )
    return api_key


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token: str = credentials.credentials

    if not token.startswith("mc_"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    key_hash = hash_api_key(token)
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT u.id, u.name, u.display_name, u.description, "
        "       u.created_at, u.last_seen, k.id AS key_id "
        "FROM user_api_keys k JOIN users u ON u.id = k.user_id "
        "WHERE k.key_hash = $1 AND k.revoked_at IS NULL",
        key_hash,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    user = dict(row)

    uid = str(user["id"])
    now = time.monotonic()
    if now - _last_seen_written.get(uid) > _LAST_SEEN_DEBOUNCE_SECONDS:
        _last_seen_written.set(uid, now)
        await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", user["id"])
        await pool.execute(
            "UPDATE user_api_keys SET last_used_at = now() WHERE id = $1", user["key_id"]
        )
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
) -> dict | None:
    if credentials is None:
        return None
    return await get_current_user(credentials)
