"""Behaviors API: named patterns tagged on trace windows, their trends, alerts and search.

Owner-scoped like the rest of the reward-model surface; another owner's id is a 404.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user
from ..services.behaviors import alerts, builtin, monitoring, search, service
from ..services.intuition import service as evals
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/behaviors",
    tags=["behaviors"],
    dependencies=[Depends(require_reward_models)],
)

Actor = Literal["user", "agent", "environment"]
Detector = Literal["rule", "llm", "agent_judge"]
Severity = Literal["low", "medium", "high"]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Alert(Body):
    threshold: int = Field(ge=1, le=100_000)
    window_hours: int = Field(default=24, ge=1, le=720)
    cooldown_hours: int = Field(default=24, ge=1, le=720)
    channels: list[Literal["slack", "email"]] = Field(default_factory=lambda: ["slack", "email"])


class CreateBehavior(Body):
    name: str = Field(min_length=1, max_length=120)
    actor: Actor
    detector: Detector = "llm"
    definition: str = Field(default="", max_length=4000)
    examples: list[str] = Field(default_factory=list, max_length=20)
    rule: dict | None = None
    severity: Severity = "medium"
    enabled: bool = True
    alert: Alert | None = None


class EditBehavior(Body):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    actor: Actor | None = None
    detector: Detector | None = None
    definition: str | None = Field(default=None, max_length=4000)
    examples: list[str] | None = Field(default=None, max_length=20)
    rule: dict | None = None
    severity: Severity | None = None
    enabled: bool | None = None
    alert: Alert | None = None


class Starters(Body):
    kinds: list[str] | None = None


class Review(Body):
    verdict: Literal["confirmed", "rejected"] | None
    note: str = Field(default="", max_length=2000)


class ManualHit(Body):
    trace_id: UUID
    start_idx: int = Field(ge=0)
    end_idx: int = Field(ge=0)
    note: str = Field(default="", max_length=2000)


class Window(Body):
    trace_id: UUID
    start_idx: int = Field(ge=0)
    end_idx: int = Field(ge=0)


class Export(Body):
    eval_id: UUID
    label: str = Field(min_length=1, max_length=64)
    windows: list[Window] = Field(min_length=1, max_length=200)


def _errors(exc: Exception):
    if isinstance(exc, service.NotFound | evals.NotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("")
async def list_behaviors(user: dict = Depends(get_current_user)):
    return {"behaviors": await service.list_behaviors(user["id"]), "rules": list(builtin.RULES)}


@router.post("", status_code=201)
async def create_behavior(body: CreateBehavior, user: dict = Depends(get_current_user)):
    try:
        return await service.create(user["id"], body.model_dump())
    except Exception as exc:
        _errors(exc)


@router.post("/starters", status_code=201)
async def install_starters(body: Starters, user: dict = Depends(get_current_user)):
    return {"created": await service.install_starters(user["id"], body.kinds)}


@router.get("/monitoring")
async def overview(
    days: int = Query(default=30, ge=1, le=180), user: dict = Depends(get_current_user)
):
    return await monitoring.overview(user["id"], days)


@router.get("/alerts")
async def recent_alerts(user: dict = Depends(get_current_user)):
    return {"alerts": await alerts.recent(user["id"])}


@router.get("/search")
async def search_traces(
    q: str | None = Query(default=None, max_length=1000),
    behaviors: list[UUID] | None = Query(default=None),
    agent: str | None = Query(default=None, max_length=200),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=25, ge=1, le=100),
    rerank: bool = False,
    user: dict = Depends(get_current_user),
):
    return await search.search(
        user["id"], q, behaviors=behaviors, agent=agent, days=days, limit=limit, rerank=rerank
    )


@router.get("/traces/{trace_id}/hits")
async def trace_hits(trace_id: UUID, user: dict = Depends(get_current_user)):
    return {"hits": await service.trace_hits(user["id"], trace_id)}


@router.post("/datasets", status_code=201)
async def export(body: Export, user: dict = Depends(get_current_user)):
    try:
        windows = [w.model_dump() for w in body.windows]
        return {"examples": await service.export(user["id"], body.eval_id, body.label, windows)}
    except Exception as exc:
        _errors(exc)


@router.post("/hits/{hit_id}/review")
async def review_hit(hit_id: UUID, body: Review, user: dict = Depends(get_current_user)):
    try:
        return await service.review(user["id"], hit_id, body.verdict, body.note)
    except Exception as exc:
        _errors(exc)


@router.get("/{behavior_id}")
async def get_behavior(behavior_id: UUID, user: dict = Depends(get_current_user)):
    try:
        return await service.get(user["id"], behavior_id)
    except Exception as exc:
        _errors(exc)


@router.patch("/{behavior_id}")
async def edit_behavior(
    behavior_id: UUID, body: EditBehavior, user: dict = Depends(get_current_user)
):
    changes = body.model_dump(exclude_unset=True)
    try:
        return await service.update(user["id"], behavior_id, changes)
    except Exception as exc:
        _errors(exc)


@router.delete("/{behavior_id}", status_code=204)
async def delete_behavior(behavior_id: UUID, user: dict = Depends(get_current_user)):
    try:
        await service.delete(user["id"], behavior_id)
    except Exception as exc:
        _errors(exc)


@router.get("/{behavior_id}/hits")
async def list_hits(
    behavior_id: UUID,
    review: Literal["confirmed", "rejected", "unreviewed"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    try:
        return {
            "hits": await service.hits(
                user["id"], behavior_id, review=review, limit=limit, offset=offset
            )
        }
    except Exception as exc:
        _errors(exc)


@router.post("/{behavior_id}/hits", status_code=201)
async def add_hit(behavior_id: UUID, body: ManualHit, user: dict = Depends(get_current_user)):
    if body.end_idx < body.start_idx:
        raise HTTPException(status_code=422, detail="end_idx must not be before start_idx")
    try:
        return await service.add_hit(
            user["id"], behavior_id, body.trace_id, body.start_idx, body.end_idx, body.note
        )
    except Exception as exc:
        _errors(exc)


@router.post("/{behavior_id}/promote", status_code=201)
async def promote(behavior_id: UUID, user: dict = Depends(get_current_user)):
    try:
        return await service.promote(user["id"], behavior_id)
    except Exception as exc:
        _errors(exc)
