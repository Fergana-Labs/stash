"""Validate Auth0-issued JWTs against the tenant's JWKS."""

import time

import httpx
from fastapi import HTTPException, status
from jose import jwt
from jose.exceptions import JWTError

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
    """Validate an Auth0 access token minted for the web app's API."""
    if not settings.AUTH0_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 not configured",
        )
    return await validate_auth0_token_for_audience(token, settings.AUTH0_AUDIENCE)


async def validate_auth0_token_for_audience(token: str, audience: str) -> dict:
    """Validate an Auth0 access token against an explicit audience.

    The remote MCP endpoint needs its own audience: with Auth0's
    resource-parameter compatibility profile enabled, Claude's tokens carry the
    MCP server's own URL in `aud`, not the web app's API identifier. Keeping the
    two audiences distinct is deliberate — a token minted for one surface is
    rejected by the other.
    """
    if not settings.AUTH0_DOMAIN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 not configured",
        )

    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
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
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return claims
