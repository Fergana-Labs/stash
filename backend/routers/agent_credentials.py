"""Connect / list / disconnect the model credential the cloud agent runs on.

A user pastes an API key for Claude (anthropic), Codex (openai), or
OpenRouter, or connects their own OpenAI-compatible local model (base URL +
model, key optional, context window and max output tokens optional — the
stored doc carries context_window/max_tokens, null when unset, and the
documented model_provider.LOCAL_DEFAULT_* constants apply), and the agent
runs their harness with it. OAuth connect flows are separate.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..services import agent_auth, agent_oauth, model_provider

router = APIRouter(prefix="/api/v1/me/agent-credentials", tags=["agent-credentials"])

_PROVIDERS = {"anthropic", "openai", "openrouter", "local"}


class ConnectRequest(BaseModel):
    provider: str
    api_key: str | None = None  # required for the three key providers; optional for local
    base_url: str | None = (
        None  # local only: OpenAI-compatible endpoint your cloud computer can reach
    )
    model: str | None = None  # local only: the model id on that endpoint
    context_window: int | None = (
        None  # local only: pi model-entry context window; unset → model_provider.LOCAL_DEFAULT_CONTEXT_WINDOW
    )
    max_tokens: int | None = (
        None  # local only: pi model-entry max output tokens; unset → model_provider.LOCAL_DEFAULT_MAX_TOKENS
    )


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
    if req.provider == "local":
        # The credential is an endpoint, not a key: an absolute http(s) base
        # URL the SPRITE can reach (the backend never dials it) plus a model id.
        parsed = urlparse((req.base_url or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "base_url must be an absolute http(s) URL your cloud computer can reach "
                    "(e.g. http://your-host:11434/v1)"
                ),
            )
        if not (req.model or "").strip():
            raise HTTPException(status_code=400, detail="model is required for the local endpoint")
        # Validate the effective pair: each value as provided, or the
        # documented constant when the user left the field unset.
        context_window = (
            req.context_window
            if req.context_window is not None
            else model_provider.LOCAL_DEFAULT_CONTEXT_WINDOW
        )
        max_tokens = (
            req.max_tokens
            if req.max_tokens is not None
            else model_provider.LOCAL_DEFAULT_MAX_TOKENS
        )
        if context_window <= 0 or max_tokens <= 0:
            raise HTTPException(
                status_code=400,
                detail="context_window and max_tokens must be positive integers",
            )
        if max_tokens >= context_window:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"max_tokens ({max_tokens}) must be less than context_window ({context_window}) "
                    "— the output budget must fit inside the context"
                ),
            )
        doc = {
            "base_url": req.base_url.strip(),
            "model": req.model.strip(),
            "api_key": (req.api_key or "").strip() or None,  # keyless endpoints are common
            "context_window": req.context_window,  # null when unset → documented constant at auth time
            "max_tokens": req.max_tokens,  # null when unset → documented constant at auth time
        }
        await agent_auth.store_credential(current_user["id"], "local", "endpoint", json.dumps(doc))
        return {"ok": True, "connected": await agent_auth.list_connected(current_user["id"])}
    if not req.api_key or not req.api_key.strip():
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
