"""Auth0 managed-session endpoints."""

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import settings
from backend.middleware import limiter
from backend.models import Auth0SessionResponse

from .jwt import validate_auth0_token
from .users import get_or_create_user_row_from_auth0

router = APIRouter(prefix="/api/v1/auth0", tags=["auth0"])

_security = HTTPBearer()


async def _fetch_userinfo(access_token: str) -> dict:
    url = f"https://{settings.AUTH0_DOMAIN}/userinfo"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code != 200:
        return {}
    return resp.json()


@router.post("/session", response_model=Auth0SessionResponse)
@limiter.limit("30/minute")
async def session(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    claims = await validate_auth0_token(credentials.credentials)
    profile = await _fetch_userinfo(credentials.credentials)
    user, created = await get_or_create_user_row_from_auth0(
        auth0_sub=claims["sub"],
        email=profile.get("email"),
        name=profile.get("name"),
        email_verified=bool(profile.get("email_verified")),
    )
    return Auth0SessionResponse(
        id=user["id"],
        name=user["name"],
        display_name=user["display_name"],
        created=created,
    )
