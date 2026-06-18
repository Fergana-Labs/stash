"""Mint short-lived, read-only dashboard tokens.

A stash-hosted dashboard runs in a sandboxed iframe that can't carry the
owner's session cookie. The owner (a real user — `mc_`/Auth0, never another
dashboard token) calls this to mint a token scoped to one workspace, which the
dashboard then uses to read that workspace's data until it expires.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import DASHBOARD_TOKEN_DEFAULT_TTL, get_current_user, mint_dashboard_token
from ..services import workspace_service

router = APIRouter(prefix="/api/v1/dashboard-tokens", tags=["dashboard-tokens"])

MAX_TTL_SECONDS = 3600


class DashboardTokenRequest(BaseModel):
    workspace_id: UUID
    ttl_seconds: int = Field(default=DASHBOARD_TOKEN_DEFAULT_TTL, ge=60, le=MAX_TTL_SECONDS)


class DashboardTokenResponse(BaseModel):
    token: str
    expires_at: int


@router.post("", response_model=DashboardTokenResponse, status_code=201)
async def create_dashboard_token(
    body: DashboardTokenRequest,
    current_user: dict = Depends(get_current_user),
) -> DashboardTokenResponse:
    # A dashboard token must not be able to mint more tokens.
    if current_user.get("dashboard_workspace_id"):
        raise HTTPException(status_code=403, detail="Dashboard tokens cannot mint tokens")
    if not await workspace_service.is_member(body.workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    token, exp = mint_dashboard_token(current_user["id"], body.workspace_id, body.ttl_seconds)
    return DashboardTokenResponse(token=token, expires_at=exp)
