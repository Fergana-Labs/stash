"""Model wizard API: guided chat sessions plus the fusion engine's actions.

The chat streams Server-Sent Events: text deltas, tool activity and progress,
and the interactive cards the wizard opens. The model routes let those cards
(and anything else) train, report, discover criteria and harden directly.
"""

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user
from ..config import settings
from ..services.intuition import fusion, wizard
from .intuitions import checked
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/model-wizard",
    tags=["model-wizard"],
    dependencies=[Depends(require_reward_models)],
)

User = Annotated[dict, Depends(get_current_user)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewSession(Body):
    model_id: UUID | None = None


class Message(Body):
    text: str = Field(min_length=1, max_length=20000)
    # "event" messages come from cards ("Labeled 12 examples") and render as a chip.
    kind: Literal["message", "event"] = "message"


class Discover(Body):
    count: int = Field(default=4, ge=1, le=6)
    guidance: str = Field(default="", max_length=2000)


class Harden(Body):
    target_label: str | None = Field(default=None, max_length=64)


@router.post("/sessions", status_code=201)
async def create_session(req: NewSession, user: User):
    return await checked(wizard.create_session(user["id"], req.model_id))


@router.get("/sessions")
async def list_sessions(user: User):
    return {"sessions": await wizard.list_sessions(user["id"])}


@router.get("/sessions/{session_id}")
async def get_session(session_id: UUID, user: User):
    session = await checked(wizard.get_session(user["id"], session_id))
    session.pop("messages")
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: UUID, user: User):
    await checked(wizard.delete_session(user["id"], session_id))


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: UUID, req: Message, user: User):
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(503, "The wizard needs ANTHROPIC_API_KEY on the server")
    await checked(wizard.get_session(user["id"], session_id))

    async def events():
        async for event in wizard.stream_turn(user["id"], session_id, req.text, req.kind):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/models/{model_id}/train")
async def train(model_id: UUID, user: User):
    return await checked(fusion.train(user["id"], model_id))


@router.get("/models/{model_id}/report")
async def report(model_id: UUID, user: User):
    return {"report": await checked(fusion.latest_report(user["id"], model_id))}


@router.post("/models/{model_id}/discover")
async def discover(model_id: UUID, req: Discover, user: User):
    return await checked(fusion.discover_criteria(user["id"], model_id, req.count, req.guidance))


@router.post("/models/{model_id}/harden")
async def harden(model_id: UUID, req: Harden, user: User):
    return await checked(fusion.harden(user["id"], model_id, req.target_label))
