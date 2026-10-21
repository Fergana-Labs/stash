"""Private customer calibration; public callers never supply cached features."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user
from ..services.rm import customer_heads as heads
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/rm/customer-heads",
    tags=["reward-models"],
    dependencies=[Depends(require_reward_models)],
)


class FitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shared_model_id: UUID
    name: str = Field(min_length=1, max_length=160)
    pair_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    l2: float = Field(default=1.0, ge=0.001, le=1000)


class LabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    winner: Literal["a", "b"]


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shared_model_id: UUID
    pair_id: UUID
    head_id: UUID | None = None


async def checked(coro):
    try:
        return await coro
    except heads.HeadMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/fit", status_code=201)
async def fit(req: FitRequest, user: dict = Depends(get_current_user)):
    return await checked(heads.fit(user["id"], req.shared_model_id, req.name, req.pair_ids, req.l2))


@router.post("/compare")
async def compare(req: CompareRequest, user: dict = Depends(get_current_user)):
    return await checked(heads.compare(user["id"], req.shared_model_id, req.pair_id, req.head_id))


@router.post("/pairs/{pair_id}/label")
async def label(pair_id: UUID, req: LabelRequest, user: dict = Depends(get_current_user)):
    return await checked(heads.label_pair(user["id"], pair_id, req.winner))


@router.delete("/pairs/{pair_id}", status_code=204)
async def revoke(pair_id: UUID, user: dict = Depends(get_current_user)):
    await checked(heads.revoke_pair(user["id"], pair_id))


@router.get("")
async def list_heads(user: dict = Depends(get_current_user)):
    return await heads.list_heads(user["id"])


@router.get("/pairs")
async def list_pairs(user: dict = Depends(get_current_user)):
    return await heads.list_pairs(user["id"])


@router.get("/scoring-runs/{run_id}")
async def scoring_run(run_id: UUID, user: dict = Depends(get_current_user)):
    return await checked(heads.scoring_run(user["id"], run_id))


@router.get("/{head_id}")
async def detail(head_id: UUID, user: dict = Depends(get_current_user)):
    return await checked(heads.detail(user["id"], head_id))
