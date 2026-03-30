import hashlib
import secrets

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_pool

security = HTTPBearer()


def generate_api_key() -> str:
    return "mc_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    key_hash = hash_api_key(credentials.credentials)
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, owner_id, notebook_id, history_id, created_at, last_seen "
        "FROM users WHERE api_key_hash = $1",
        key_hash,
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    # Update last_seen
    await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", row["id"])
    return dict(row)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> dict | None:
    if credentials is None:
        return None
    return await get_current_user(credentials)


async def get_user_from_api_key(api_key: str) -> dict | None:
    key_hash = hash_api_key(api_key)
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, owner_id, notebook_id, history_id, created_at, last_seen "
        "FROM users WHERE api_key_hash = $1",
        key_hash,
    )
    if row:
        return dict(row)
    return None
