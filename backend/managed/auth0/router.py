"""POST /api/v1/auth0/exchange — swap an Auth0 access token for an octopus api_key."""

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import settings
from backend.middleware import limiter
from backend.models import UserRegisterResponse

from .jwt import validate_auth0_token
from .users import get_or_create_user_from_auth0

router = APIRouter(prefix="/api/v1/auth0", tags=["auth0"])

_security = HTTPBearer()


async def _fetch_userinfo(access_token: str) -> dict:
    url = f"https://{settings.AUTH0_DOMAIN}/userinfo"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code != 200:
        return {}
    return resp.json()


@router.post("/exchange", response_model=UserRegisterResponse)
@limiter.limit("30/minute")
async def exchange(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    claims = await validate_auth0_token(credentials.credentials)
    profile = await _fetch_userinfo(credentials.credentials)
    device = request.query_params.get("device", "").strip()[:96]
    key_name = f"CLI ({device})" if device else "Auth0 login"
    user, api_key = await get_or_create_user_from_auth0(
        auth0_sub=claims["sub"],
        email=profile.get("email"),
        name=profile.get("name"),
        key_name=key_name,
    )
    return UserRegisterResponse(
        id=user["id"],
        name=user["name"],
        display_name=user["display_name"],
        api_key=api_key,
    )
