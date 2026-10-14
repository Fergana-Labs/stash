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
from ..services.intuition import curation, fusion, wizard
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


class Brief(Body):
    model_config = ConfigDict(extra="allow")


class Triage(Body):
    action: Literal["looks_right", "escalate", "ignore"]
    note: str = Field(default="", max_length=2000)


class Resolve(Body):
    label: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=2000)
    pin: bool = False


class Calibration(Body):
    example_ids: list[UUID] | None = None
    on: bool = True


class NewLink(Body):
    reviewer: str = Field(min_length=1, max_length=80)


class Rating(Body):
    label: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=2000)


class FromCorrections(Body):
    count: int = Field(default=3, ge=1, le=6)


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


# ── Curation: brief, queues, calibration, topics, golden-set health ───────


@router.get("/models/{model_id}/brief")
async def get_brief(model_id: UUID, user: User):
    return await checked(curation.get_brief(user["id"], model_id))


@router.patch("/models/{model_id}/brief")
async def save_brief(model_id: UUID, req: Brief, user: User):
    return await checked(curation.save_brief(user["id"], model_id, req.model_dump()))


@router.get("/models/{model_id}/queue/{which}")
async def queue(
    model_id: UUID, which: Literal["triage", "expert"], user: User, topic: str | None = None
):
    return {"items": await checked(curation.queue(user["id"], model_id, which, topic))}


@router.post("/models/{model_id}/predictions/{prediction_id}/triage")
async def triage(model_id: UUID, prediction_id: UUID, req: Triage, user: User):
    return await checked(curation.triage(user["id"], model_id, prediction_id, req.action, req.note))


@router.post("/models/{model_id}/predictions/{prediction_id}/resolve")
async def resolve(model_id: UUID, prediction_id: UUID, req: Resolve, user: User):
    return await checked(
        curation.resolve(user["id"], model_id, prediction_id, req.label, req.note, req.pin)
    )


@router.post("/models/{model_id}/calibration")
async def calibration(model_id: UUID, req: Calibration, user: User):
    return await checked(curation.set_calibration(user["id"], model_id, req.example_ids, req.on))


@router.get("/models/{model_id}/agreement")
async def agreement(model_id: UUID, user: User):
    return await checked(curation.agreement(user["id"], model_id))


@router.get("/models/{model_id}/review-links")
async def list_links(model_id: UUID, user: User):
    return {"links": await checked(curation.list_links(user["id"], model_id))}


@router.post("/models/{model_id}/review-links", status_code=201)
async def create_link(model_id: UUID, req: NewLink, user: User):
    return await checked(curation.create_link(user["id"], model_id, req.reviewer))


@router.delete("/models/{model_id}/review-links/{token}", status_code=204)
async def revoke_link(model_id: UUID, token: str, user: User):
    await checked(curation.revoke_link(user["id"], model_id, token))


@router.get("/models/{model_id}/topics")
async def topics(model_id: UUID, user: User):
    return await checked(curation.topic_stats(user["id"], model_id))


@router.post("/models/{model_id}/topics")
async def refresh_topics(model_id: UUID, user: User):
    return await checked(curation.refresh_topics(user["id"], model_id))


@router.get("/models/{model_id}/health")
async def health(model_id: UUID, user: User):
    return await checked(curation.health(user["id"], model_id))


@router.post("/models/{model_id}/criteria-from-corrections")
async def criteria_from_corrections(model_id: UUID, req: FromCorrections, user: User):
    return await checked(curation.criteria_from_corrections(user["id"], model_id, req.count))


# Invited reviewers have no account: the unguessable token is the credential,
# and it can only read the calibration items and write that reviewer's labels.
public_router = APIRouter(prefix="/api/v1/review-links", tags=["model-wizard"])


@public_router.get("/{token}")
async def review_link(token: str):
    return await checked(curation.link_view(token))


@public_router.post("/{token}/items/{example_id}")
async def rate(token: str, example_id: UUID, req: Rating):
    return await checked(curation.rate(token, example_id, req.label, req.note))
