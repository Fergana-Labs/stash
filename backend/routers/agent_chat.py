"""Multi-turn agent chat for the Agents view.

A chat is just a workspace Session: each turn is persisted as a history event
(see ask_service.stream_chat), so chats are stored, reloadable, and show up in
Sessions alongside CLI transcripts. The frontend holds a session_id per tab and
streams replies from here.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..config import settings
from ..services import ask_service, workspace_service

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/agent-chat", tags=["agent-chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    # Omitted for the first message of a new chat — the server mints one.
    session_id: str | None = None


async def _require_member(workspace_id: UUID, user_id: UUID) -> dict:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    workspace = await workspace_service.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.post("")
async def chat(
    workspace_id: UUID,
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    workspace = await _require_member(workspace_id, current_user["id"])
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="The agent is not configured (ANTHROPIC_API_KEY unset).",
        )
    session_id = req.session_id or f"agent-{uuid4().hex}"
    return StreamingResponse(
        ask_service.stream_chat(
            workspace_id, workspace["name"], current_user["id"], session_id, req.message
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}")
async def get_chat(
    workspace_id: UUID,
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """The chat's turns as [{role, content}], for restoring a tab."""
    await _require_member(workspace_id, current_user["id"])
    messages = await ask_service._load_history(workspace_id, session_id, current_user["id"])
    return {"session_id": session_id, "messages": messages}
