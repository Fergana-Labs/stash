"""Continuous improvement API shared by the product UI and MCP clients."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..auth import get_current_user
from ..database import get_pool
from ..services.rm import optimization as service
from .reward_models import require_reward_models
from .workbench import checked, require_workbench

router = APIRouter(
    prefix="/api/v1/rm/optimizations",
    tags=["optimization"],
    dependencies=[Depends(require_reward_models), Depends(require_workbench)],
)


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Metric(Body):
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(default="", max_length=40)
    direction: Literal["higher", "lower"] = "higher"
    minimum: float = 0
    maximum: float = 1
    regression_tolerance: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_range(self):
        if self.minimum >= self.maximum:
            raise ValueError("Metric maximum must be greater than minimum")
        if self.regression_tolerance > self.maximum - self.minimum:
            raise ValueError("Regression tolerance cannot exceed the metric range")
        return self


class Create(Body):
    name: str = Field(min_length=1, max_length=160)
    reward_model_id: UUID
    agent: str = Field(min_length=1, max_length=160)
    scope: str = Field(min_length=1, max_length=2000)
    initial_prompt: str = Field(default="", max_length=12000)
    metric: Metric
    runs_per_arm: int = Field(default=20, ge=5, le=500)
    max_rounds: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def no_marker(self):
        if "stash-optimization" in self.initial_prompt:
            raise ValueError("Initial instructions contain reserved delivery markers")
        return self


class Control(Body):
    action: Literal["pause", "resume", "rollback"]
    revision_id: UUID | None = None


class Assign(Body):
    work_key: str = Field(min_length=1, max_length=300)
    agent: str = Field(min_length=1, max_length=160)
    scope: str = Field(min_length=1, max_length=2000)
    agent_version: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, min_length=1, max_length=300)


class Submit(Body):
    trace_id: UUID | None = None
    session_id: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def one_trace(self):
        if bool(self.trace_id) == bool(self.session_id):
            raise ValueError("Provide either trace_id or the captured session_id")
        return self


class Outcome(Body):
    value: float
    source: str = Field(min_length=1, max_length=2000)


class Abandon(Body):
    reason: str = Field(min_length=1, max_length=2000)


@router.get("")
async def list_optimizations(user=Depends(get_current_user)):
    return await service.list_programs(user["id"])


@router.post("", status_code=201)
async def create_optimization(body: Create, user=Depends(get_current_user)):
    return await checked(service.create(user["id"], body.model_dump()))


@router.get("/runs/{run_id}")
async def run_detail(run_id: UUID, user=Depends(get_current_user)):
    return await checked(service.run_detail(user["id"], run_id))


@router.post("/runs/{run_id}/trace")
async def submit(run_id: UUID, body: Submit, user=Depends(get_current_user)):
    trace_id = body.trace_id
    if trace_id is None:
        trace_id = await get_pool().fetchval(
            "SELECT id FROM rm_traces WHERE owner_user_id=$1 AND external_id=$2",
            user["id"],
            body.session_id,
        )
    if trace_id is None:
        from fastapi import HTTPException

        raise HTTPException(
            404, "The session trace has not been uploaded yet; retry after capture completes"
        )
    return await checked(service.submit(user["id"], run_id, trace_id))


@router.post("/runs/{run_id}/outcome")
async def outcome(run_id: UUID, body: Outcome, user=Depends(get_current_user)):
    return await checked(service.record_outcome(user["id"], run_id, body.value, body.source))


@router.post("/runs/{run_id}/abandon")
async def abandon(run_id: UUID, body: Abandon, user=Depends(get_current_user)):
    return await checked(service.abandon(user["id"], run_id, body.reason))


@router.get("/{optimization_id}")
async def detail(optimization_id: UUID, user=Depends(get_current_user)):
    return await checked(service.detail(user["id"], optimization_id))


@router.post("/{optimization_id}/control")
async def control(optimization_id: UUID, body: Control, user=Depends(get_current_user)):
    return await checked(
        service.control(user["id"], optimization_id, body.action, body.revision_id)
    )


@router.post("/{optimization_id}/runs")
async def assign(optimization_id: UUID, body: Assign, user=Depends(get_current_user)):
    return await checked(service.assign(user["id"], optimization_id, body.model_dump()))
