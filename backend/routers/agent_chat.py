"""Multi-turn agent chat for the Agents view.

A chat is just a Session: each turn is persisted as a history event (see
sprite_agent_service.stream_chat), so chats are stored, reloadable, and show
up in Sessions alongside CLI transcripts. The frontend holds a session_id per
tab and streams replies from here. Turns execute as Claude Code on the user's
cloud computer (sprite_service).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services import agent_auth, agent_service, memory_service, sprite_agent_service

router = APIRouter(prefix="/api/v1/me/agent-chat", tags=["agent-chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    # Omitted for the first message of a new chat — the server mints one.
    session_id: str | None = None
    # Which configured agent runs this chat (its model + persona). Default agent
    # if omitted.
    agent_id: str | None = None


@router.post("")
async def chat(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    agent = (
        await agent_service.get_agent(current_user["id"], UUID(req.agent_id))
        if req.agent_id
        else await agent_service.get_or_create_default(current_user["id"])
    )
    # Resolve the harness + credentials up front so an unconnected free user
    # gets a clean 402 instead of a stream that dies mid-flight.
    try:
        auth = await agent_auth.resolve(current_user["id"], agent["model_provider"])
    except agent_auth.NeedsAuth:
        raise HTTPException(
            status_code=402,
            detail="Connect your Claude, Codex, or OpenRouter key in settings, "
            "or upgrade to Pro to use the managed agent.",
        )
    except agent_auth.ProviderNotConfigured:
        raise HTTPException(status_code=503, detail="The agent is not configured.")
    scope_name = current_user["display_name"] or current_user["name"]
    session_id = req.session_id or f"agent-{uuid4().hex}"
    return StreamingResponse(
        sprite_agent_service.stream_chat(
            owner_user_id,
            scope_name,
            current_user["id"],
            session_id,
            req.message,
            auth,
            agent["system_prompt"],
            agent_name=agent["name"],
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RunRequest(BaseModel):
    agent_id: str


@router.post("/run")
async def run_now(
    req: RunRequest,
    current_user: dict = Depends(get_current_user),
):
    """Run a prompt-scheduled agent on demand, streamed live like a chat turn.
    The server builds the prompt from schedule_prompt, so the run is identical
    to what the beat task fires. The turn runs detached (see stream_chat), so
    closing the tab doesn't kill it.

    Curator runs are refused here: they enqueue on the worker via POST
    /me/memory/recompute — the same path the daily schedule and the CLI use —
    so credit metering and the curated_through watermark stay in one place."""
    agent = await agent_service.get_agent(current_user["id"], UUID(req.agent_id))
    if agent["run_mode"] != "scheduled":
        raise HTTPException(status_code=400, detail="Only scheduled agents can be run on demand.")
    if agent["is_curator"]:
        raise HTTPException(
            status_code=400,
            detail="Curator runs execute on the worker — use POST /me/memory/recompute.",
        )
    if not agent["schedule_prompt"]:
        raise HTTPException(status_code=400, detail="This agent has no scheduled prompt to run.")
    try:
        auth = await agent_auth.resolve(current_user["id"], agent["model_provider"])
    except agent_auth.NeedsAuth:
        raise HTTPException(
            status_code=402,
            detail="Connect your Claude, Codex, or OpenRouter key in settings, "
            "or upgrade to Pro to use the managed agent.",
        )
    except agent_auth.ProviderNotConfigured:
        raise HTTPException(status_code=503, detail="The agent is not configured.")

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    session_id, message = await sprite_agent_service.build_scheduled_turn(agent, stamp)
    scope_name = current_user["display_name"] or current_user["name"]
    return StreamingResponse(
        sprite_agent_service.stream_chat(
            current_user["id"],
            scope_name,
            current_user["id"],
            session_id,
            message,
            auth,
            agent["system_prompt"],
            agent_name=agent["name"],
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _require_own_session(session_id: str, current_user: dict) -> None:
    """A running turn always has at least its user_message event, so an empty
    read means the session isn't this user's (or doesn't exist)."""
    events = await memory_service.read_session_events(
        current_user["id"], session_id, current_user["id"]
    )
    if not events:
        raise HTTPException(status_code=404, detail="No such chat.")


@router.get("/{session_id}/status")
async def turn_status(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Whether a turn is currently executing in this chat — lets a client
    (the CLI's watch/stop) monitor runs started anywhere, web or Slack or
    a schedule."""
    await _require_own_session(session_id, current_user)
    return {
        "session_id": session_id,
        "running": await sprite_agent_service.turn_running(session_id),
    }


@router.post("/{session_id}/stop")
async def stop_turn(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Stop the session's running turn. The flag is picked up by the turn's
    stream loop, which kills the harness exec on the box."""
    await _require_own_session(session_id, current_user)
    if not await sprite_agent_service.request_stop(session_id):
        raise HTTPException(status_code=409, detail="No turn is running in this chat.")
    return {"stopping": True}


@router.get("/{session_id}")
async def get_chat(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """The chat's turns for restoring a tab: [{role, content}] plus the turn's
    tool calls as {role: "tool", tool_name, metadata} rows in order — the
    client folds them into the citations strip, matching the live stream."""
    owner_user_id = current_user["id"]
    events = await memory_service.read_session_events(owner_user_id, session_id, current_user["id"])
    messages = []
    for e in events:
        content = (e.get("content") or "").strip()
        kind = e["event_type"]
        if kind in ("user_message", "assistant_message") and content:
            messages.append({"role": kind.removesuffix("_message"), "content": content})
        elif kind == "tool_use":
            messages.append(
                {
                    "role": "tool",
                    "content": content,
                    "tool_name": e.get("tool_name"),
                    "metadata": e.get("metadata") or {},
                }
            )
    return {"session_id": session_id, "messages": messages}
