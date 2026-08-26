"""Connect / list / disconnect the local endpoint credential the workspace's agents run on.

Workspace agents (the developer-wiki curator above all, and every agent that
runs under the workspace scope) execute under the workspace's scope account —
a login-less user row that can never connect a credential for itself. So the
operator connects from the Developer Platform console: the console sends
X-Stash-Scope, and the credential is stored on the scope account, where
agent_auth's auto-resolution already makes the workspace's agents run on PI
against that endpoint.

Only the local endpoint is connectable here (a login-less account has no
OAuth flow), and the shape is the personal local flow's: base URL + model,
key optional.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_scope
from ..services import agent_auth
from .developer import _require_active_workspace

router = APIRouter(
    prefix="/api/v1/me/developer/agent-credentials", tags=["developer-agent-credentials"]
)


class ConnectLocalRequest(BaseModel):
    base_url: str  # OpenAI-compatible endpoint your cloud computer can reach
    model: str  # the model id on that endpoint
    api_key: str | None = None  # keyless endpoints are common


@router.get("")
async def list_credentials(scope_user_id: UUID = Depends(get_scope)):
    """The local endpoint the workspace's agents run on (never returns the secret)."""
    await _require_active_workspace(scope_user_id)
    return {"connected": await agent_auth.list_connected(scope_user_id)}


@router.post("")
async def connect_local(req: ConnectLocalRequest, scope_user_id: UUID = Depends(get_scope)):
    await _require_active_workspace(scope_user_id)
    try:
        secret = agent_auth.local_endpoint_secret(req.base_url, req.model, req.api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await agent_auth.store_credential(scope_user_id, "local", "endpoint", secret)
    return {"ok": True, "connected": await agent_auth.list_connected(scope_user_id)}


@router.delete("/local")
async def disconnect_local(scope_user_id: UUID = Depends(get_scope)):
    await _require_active_workspace(scope_user_id)
    await agent_auth.delete_credential(scope_user_id, "local")
    return {"ok": True, "connected": await agent_auth.list_connected(scope_user_id)}
