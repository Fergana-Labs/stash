"""POST /api/v1/auth0/exchange — swap an Auth0 access token for an octopus api_key."""

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.middleware import limiter
from backend.models import UserRegisterResponse

from .jwt import validate_auth0_token
from .users import get_or_create_user_from_auth0

router = APIRouter(prefix="/api/v1/auth0", tags=["auth0"])

_security = HTTPBearer()


@router.post("/exchange", response_model=UserRegisterResponse)
@limiter.limit("30/minute")
async def exchange(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    claims = await validate_auth0_token(credentials.credentials)
    user, api_key = await get_or_create_user_from_auth0(
        auth0_sub=claims["sub"],
        email=claims.get("email"),
        name=claims.get("name"),
    )
    return UserRegisterResponse(
        id=user["id"],
        name=user["name"],
        display_name=user["display_name"],
        api_key=api_key,
    )
