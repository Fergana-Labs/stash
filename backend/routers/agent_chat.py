"""Multi-turn agent chat for the Agents view.

A chat is just a Session: each turn is persisted as a history event (see
sprite_agent_service.stream_chat), so chats are stored, reloadable, and show
up in Sessions alongside CLI transcripts. The frontend holds a session_id per
tab and streams replies from here. Turns execute as Claude Code on the user's
cloud computer (sprite_service).
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..config import settings
from ..services import sprite_agent_service

router = APIRouter(prefix="/api/v1/me/agent-chat", tags=["agent-chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    # Omitted for the first message of a new chat — the server mints one.
    session_id: str | None = None


@router.post("")
async def chat(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="The agent is not configured (ANTHROPIC_API_KEY unset).",
        )
    scope_name = current_user["display_name"] or current_user["name"]
    session_id = req.session_id or f"agent-{uuid4().hex}"
    return StreamingResponse(
        sprite_agent_service.stream_chat(
            owner_user_id, scope_name, current_user["id"], session_id, req.message
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}")
async def get_chat(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """The chat's turns as [{role, content}], for restoring a tab."""
    owner_user_id = current_user["id"]
    messages = await sprite_agent_service._load_history(
        owner_user_id, session_id, current_user["id"]
    )
    return {"session_id": session_id, "messages": messages}
