import asyncio
import hashlib
import re
import secrets
import time
from functools import lru_cache

import bcrypt
import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_pool

security = HTTPBearer()

_LAST_SEEN_DEBOUNCE_SECONDS = 60
_LAST_SEEN_CACHE_SIZE = 4096

# Auth0 user name generation: strip everything non-alphanumeric except _ and -
_SAFE_USERNAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


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


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------------------------------------------------------------------------
# Auth0 JWT verification
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_jwks_client() -> pyjwt.PyJWKClient:
    from .config import settings
    if not settings.AUTH0_DOMAIN:
        raise RuntimeError("AUTH0_DOMAIN is not configured")
    return pyjwt.PyJWKClient(
        f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json",
        cache_jwk_set=True,
        lifespan=3600,
    )


async def _verify_auth0_token(token: str) -> dict:
    """Verify an Auth0 JWT and return the decoded payload."""
    from .config import settings
    if not settings.AUTH0_DOMAIN or not settings.AUTH0_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Auth0 is not configured on this server",
        )
    loop = asyncio.get_event_loop()
    client = _get_jwks_client()
    try:
        signing_key = await loop.run_in_executor(
            None, client.get_signing_key_from_jwt, token
        )
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.AUTH0_AUDIENCE,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}")
    return payload


def _make_auth0_username(sub: str, email: str | None, name: str | None) -> str:
    """Derive a safe Octopus username from Auth0 claims."""
    # Prefer email prefix, then name, then sub fragment
    if email:
        candidate = email.split("@")[0]
    elif name:
        candidate = name
    else:
        # sub looks like "auth0|abc123" — take the part after |
        candidate = sub.split("|")[-1]

    candidate = _SAFE_USERNAME_RE.sub("_", candidate)[:48].strip("_") or "user"
    return candidate


async def _get_or_create_auth0_user(payload: dict) -> dict:
    """Look up a user by auth0_sub; JIT-provision on first login."""
    sub: str = payload["sub"]
    email: str | None = payload.get("email")
    name: str | None = payload.get("name")
    pool = get_pool()

    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, created_at, last_seen "
        "FROM users WHERE auth0_sub = $1",
        sub,
    )
    if row:
        return dict(row)

    # First login — provision a new human account.
    # api_key_hash is NOT NULL so we generate a random placeholder; the user
    # authenticates via Auth0 JWT and never needs this raw key.
    placeholder_key_hash = hash_api_key(secrets.token_urlsafe(32))
    base_username = _make_auth0_username(sub, email, name)
    display = (name or (email.split("@")[0] if email else base_username))[:128]

    # Resolve username collisions by appending a counter.
    username = base_username
    for attempt in range(1, 20):
        existing = await pool.fetchval(
            "SELECT id FROM users WHERE name = $1", username
        )
        if not existing:
            break
        username = f"{base_username}{attempt}"
    else:
        username = f"{base_username}_{secrets.token_urlsafe(4)}"

    row = await pool.fetchrow(
        "INSERT INTO users "
        "  (name, display_name, type, api_key_hash, auth0_sub, description) "
        "VALUES ($1, $2, 'human', $3, $4, '') "
        "RETURNING id, name, display_name, type, description, "
        "          created_at, last_seen",
        username, display, placeholder_key_hash, sub,
    )
    return dict(row)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token: str = credentials.credentials

    if token.startswith("mc_"):
        # --- API key path (CLI) ---
        key_hash = hash_api_key(token)
        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT id, name, display_name, type, description, "
            "       created_at, last_seen "
            "FROM users WHERE api_key_hash = $1",
            key_hash,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
            )
        user = dict(row)
    else:
        # --- Auth0 JWT path ---
        payload = await _verify_auth0_token(token)
        user = await _get_or_create_auth0_user(payload)

    uid = str(user["id"])
    now = time.monotonic()
    if now - _last_seen_written.get(uid) > _LAST_SEEN_DEBOUNCE_SECONDS:
        _last_seen_written.set(uid, now)
        pool = get_pool()
        await pool.execute(
            "UPDATE users SET last_seen = now() WHERE id = $1", user["id"]
        )
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> dict | None:
    if credentials is None:
        return None
    return await get_current_user(credentials)


async def get_user_from_api_key(token: str) -> dict | None:
    """Used by WebSocket endpoints that pass the token as a query param.

    Accepts both mc_ API keys and Auth0 JWTs.
    """
    if token.startswith("mc_"):
        key_hash = hash_api_key(token)
        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT id, name, display_name, type, description, "
            "       created_at, last_seen "
            "FROM users WHERE api_key_hash = $1",
            key_hash,
        )
        return dict(row) if row else None

    # Try Auth0 JWT
    try:
        payload = await _verify_auth0_token(token)
        return await _get_or_create_auth0_user(payload)
    except Exception:
        return None
