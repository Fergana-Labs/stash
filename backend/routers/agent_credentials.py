"""Connect / list / disconnect the model credential the cloud agent runs on.

A user pastes an API key for Claude (anthropic), Codex (openai), or OpenRouter,
and the agent runs their harness with it. OAuth connect flows are separate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..services import agent_auth, agent_oauth

router = APIRouter(prefix="/api/v1/me/agent-credentials", tags=["agent-credentials"])

_PROVIDERS = {"anthropic", "openai", "openrouter"}


class ConnectRequest(BaseModel):
    provider: str
    api_key: str


class OAuthStartRequest(BaseModel):
    provider: str  # 'anthropic' (Claude) or 'openai' (Codex)


class OAuthFinishRequest(BaseModel):
    provider: str
    code: str  # the code (or code#state, or full redirect URL) the user pasted
    state: str


@router.get("")
async def list_credentials(current_user: dict = Depends(get_current_user)):
    """Which providers this user has connected (never returns the secrets)."""
    return {"connected": await agent_auth.list_connected(current_user["id"])}


@router.post("")
async def connect(req: ConnectRequest, current_user: dict = Depends(get_current_user)):
    if req.provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"unknown provider: {req.provider}")
    if not req.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key is required")
    await agent_auth.store_credential(
        current_user["id"], req.provider, "api_key", req.api_key.strip()
    )
    return {"ok": True, "connected": await agent_auth.list_connected(current_user["id"])}


@router.post("/oauth/start")
async def oauth_start(req: OAuthStartRequest, current_user: dict = Depends(get_current_user)):
    """Begin a Claude/Codex OAuth connect. The frontend opens authorize_url in a
    popup; the user approves and pastes the code the provider displays."""
    return agent_oauth.start(current_user["id"], req.provider)


@router.post("/oauth/finish")
async def oauth_finish(req: OAuthFinishRequest, current_user: dict = Depends(get_current_user)):
    """Exchange the pasted code and store the OAuth credential."""
    await agent_oauth.finish(current_user["id"], req.provider, req.code, req.state)
    return {"ok": True, "connected": await agent_auth.list_connected(current_user["id"])}


@router.delete("/{provider}")
async def disconnect(provider: str, current_user: dict = Depends(get_current_user)):
    await agent_auth.delete_credential(current_user["id"], provider)
    return {"ok": True, "connected": await agent_auth.list_connected(current_user["id"])}
