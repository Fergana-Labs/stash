"""Operator-only shared evaluator corpus, training and release controls."""

from dataclasses import asdict
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..database import get_pool
from ..services.rm import datasets, evaluator, feedback
from ..services.rm.adapters import CanonicalStep
from .admin import require_admin_token

router = APIRouter(
    prefix="/api/v1/admin/rm", tags=["admin"], dependencies=[Depends(require_admin_token)]
)


class ExampleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_user_id: UUID
    context: list[CanonicalStep]
    task_context: dict = Field(default_factory=dict)
    chosen: CanonicalStep
    rejected: CanonicalStep
    task_group: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=100)
    agent: str = Field(min_length=1, max_length=100)
    partition: Literal["train", "eval"]
    source: Literal["human", "verified_outcome"]
    evidence: str = Field(min_length=1)
    permission_reference: str = Field(min_length=1)


class CandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_user_id: UUID
    name: str = Field(min_length=1, max_length=200)
    base_model: str = "Qwen/Qwen3-0.6B"
    epochs: int = Field(default=1, ge=1, le=10)


class ReleaseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AutomationRequest(CandidateRequest):
    name: str = "Stash evaluator candidate"
    enabled: bool
    min_new_examples: int = Field(default=100, ge=2, le=100000)
    interval_hours: int = Field(default=24, ge=1, le=8760)
    auto_promote: bool = False


async def checked(coro):
    try:
        return await coro
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/examples", status_code=201)
async def add_example(req: ExampleRequest) -> dict:
    chosen, rejected = asdict(req.chosen), asdict(req.rejected)
    if not all(feedback.is_assistant_action(s) for s in (chosen, rejected)):
        raise HTTPException(status_code=422, detail="Both alternatives must be assistant actions")
    if not await get_pool().fetchval("SELECT 1 FROM users WHERE id = $1", req.owner_user_id):
        raise HTTPException(status_code=404, detail="Owner account not found")
    context = [asdict(s) for s in req.context]
    pair = {
        "chosen": datasets.render_action_context([*context, chosen], req.task_context),
        "rejected": datasets.render_action_context([*context, rejected], req.task_context),
        "action_type": "tool_call"
        if chosen.get("tool_name") or rejected.get("tool_name")
        else "response",
    }
    async with get_pool().acquire() as conn, conn.transaction():
        example_id = await checked(
            evaluator.insert_example(
                conn,
                req.owner_user_id,
                pair,
                task_group=req.task_group,
                domain=req.domain,
                agent=req.agent,
                partition=req.partition,
                provenance={
                    "source": req.source,
                    "evidence": req.evidence,
                    "permission": req.permission_reference,
                },
            )
        )
    if example_id is None:
        raise HTTPException(status_code=409, detail="Comparison already exists")
    return {"id": example_id}


@router.get("/examples")
async def list_examples(
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
) -> list[dict]:
    return [
        dict(r)
        for r in await get_pool().fetch(
            "SELECT * FROM rm_training_examples ORDER BY created_at, id LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
    ]


@router.delete("/examples/{example_id}", status_code=204)
async def delete_example(example_id: UUID) -> None:
    await get_pool().execute("DELETE FROM rm_training_examples WHERE id = $1", example_id)


@router.post("/candidates", status_code=202)
async def create_candidate(req: CandidateRequest) -> dict:
    return await checked(
        evaluator.create_candidate(req.owner_user_id, req.name, req.base_model, req.epochs)
    )


@router.get("/candidates")
async def list_candidates() -> list[dict]:
    return [
        dict(r)
        for r in await get_pool().fetch(
            "SELECT id,name,status,error,metrics,release_report,parent_model_id,created_at FROM rm_reward_models WHERE scope = 'shared' ORDER BY created_at DESC LIMIT 100"
        )
    ]


@router.get("/candidates/{model_id}")
async def get_candidate(model_id: UUID) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM rm_reward_models WHERE id = $1 AND scope = 'shared'", model_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return dict(row)


@router.post("/candidates/{model_id}/promote")
async def promote(model_id: UUID, req: ReleaseRequest) -> dict:
    return await checked(evaluator.promote(model_id, req.reason))


@router.post("/candidates/{model_id}/rollback")
async def rollback(model_id: UUID, req: ReleaseRequest) -> dict:
    return await checked(evaluator.promote(model_id, req.reason, rollback=True))


@router.get("/releases")
async def list_releases() -> list[dict]:
    return [
        dict(r)
        for r in await get_pool().fetch(
            "SELECT * FROM rm_evaluator_releases ORDER BY registry_revision DESC LIMIT 100"
        )
    ]


@router.get("/automation")
async def get_automation() -> dict:
    row = await get_pool().fetchrow("SELECT * FROM rm_evaluator_automation WHERE singleton")
    return dict(row) if row else {"enabled": False}


@router.put("/automation")
async def configure_automation(req: AutomationRequest) -> dict:
    return await checked(evaluator.configure_automation(req.model_dump(exclude={"name"})))
