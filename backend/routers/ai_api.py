"""Grounded AI over a workspace's data — authenticated users only.

Two primitives a dashboard can drop in:
- `POST /ai/v1/{ws}/search` — retrieval across the workspace's pages/sessions/
  sources (wraps source_service.search_all), scoped to the user.
- `POST /ai/v1/{ws}/chat` — the grounded agent with **read-only** tools, streamed
  in the Vercel AI SDK data-stream format so `useChat({ api })` works drop-in.

Both require a real user token (mc_/dashboard/Auth0); publishable `pk_` keys are
rejected by get_current_user, so nobody runs the agent on the owner's tokens
from a public page. Mutations belong on the data API, not the chat box.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..config import settings
from ..services import ai_sdk, llm, prompts, source_service, tool_loop, workspace_service

router = APIRouter(prefix="/ai/v1/{workspace_id}", tags=["ai"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    source: str | None = None
    limit: int = Field(20, ge=1, le=100)


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    parts: list[dict] | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)


async def _require_member(workspace_id: UUID, user_id: UUID) -> dict:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    workspace = await workspace_service.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.post("/search")
async def search(
    workspace_id: UUID,
    body: SearchRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    await _require_member(workspace_id, current_user["id"])
    results = await source_service.search_all(
        workspace_id, current_user["id"], body.query, body.source, body.limit
    )
    return {"results": results or []}


def _message_text(message: ChatMessage) -> str:
    if message.content is not None:
        return message.content
    # AI SDK v5 sends typed parts; concatenate the text ones.
    return "".join(p.get("text", "") for p in (message.parts or []) if p.get("type") == "text")


def _to_history(messages: list[ChatMessage]) -> list[dict]:
    history: list[dict] = []
    for message in messages:
        if message.role not in ("user", "assistant"):
            continue
        text = _message_text(message).strip()
        if text:
            history.append({"role": message.role, "content": text})
    return history


@router.post("/chat")
async def chat(
    workspace_id: UUID,
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    workspace = await _require_member(workspace_id, current_user["id"])
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503, detail="The agent is not configured (ANTHROPIC_API_KEY unset)"
        )

    history = _to_history(body.messages)
    if not history:
        raise HTTPException(status_code=400, detail="No user message")

    sources = await source_service.list_sources(workspace_id, current_user["id"])
    system = prompts.render_ask_system(workspace["name"], sources)
    events = tool_loop.stream_tool_loop(
        tier=llm.ModelTier.QUALITY,
        system=system,
        history=history,
        workspace_id=workspace_id,
        user_id=current_user["id"],
        tool_set=prompts.ASK_TOOL_SET,
    )
    return StreamingResponse(
        ai_sdk.to_data_stream(events),
        media_type="text/event-stream",
        headers=ai_sdk.DATA_STREAM_HEADERS,
    )
