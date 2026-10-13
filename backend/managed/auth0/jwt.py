"""Validate Auth0-issued JWTs against the tenant's JWKS."""

import time

import httpx
import jwt
from fastapi import HTTPException, status

from backend.config import settings

_JWKS_TTL_SECONDS = 600

_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


async def _fetch_jwks() -> dict:
    now = time.monotonic()
    if _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < _JWKS_TTL_SECONDS:
        return _jwks_cache["keys"]
    url = f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        keys = resp.json()
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


async def validate_auth0_token(token: str) -> dict:
    """Validate an Auth0 access token. Returns the decoded claims."""
    if not settings.AUTH0_DOMAIN or not settings.AUTH0_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 not configured",
        )

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing kid")

    jwks = await _fetch_jwks()
    signing_key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not signing_key:
        # Key rotation — bust cache once and retry
        _jwks_cache["keys"] = None
        jwks = await _fetch_jwks()
        signing_key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not signing_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown key id")

    try:
        public_key = jwt.PyJWK.from_dict(signing_key, algorithm="RS256").key
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.AUTH0_AUDIENCE,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return claims
