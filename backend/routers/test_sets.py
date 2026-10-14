"""Test sets API: regression tests for agents.

Create a set, add cases (by hand, from a file, or from a production trace),
post a version's outputs as a run, and read the run's verdicts against its
baseline. `stash test run` drives the same endpoints from CI.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user
from ..services.test_sets import service
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/test-sets",
    tags=["test-sets"],
    dependencies=[Depends(require_reward_models)],
)

CaseInput = str | list[dict]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scorer(Body):
    type: Literal["expected", "eval"]
    eval_id: UUID | None = None
    pass_labels: list[str] = Field(default_factory=list)


class CreateSet(Body):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    scorers: list[Scorer] | None = None
    max_regressions: int = Field(default=0, ge=0)


class EditSet(Body):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    scorers: list[Scorer] | None = None
    max_regressions: int | None = Field(default=None, ge=0)
    baseline_run_id: UUID | None = None


class Case(Body):
    name: str = Field(default="", max_length=200)
    input: CaseInput
    expected: str | None = Field(default=None, max_length=20_000)


class Cases(Body):
    cases: list[Case] = Field(min_length=1, max_length=2_000)


class FromTrace(Body):
    trace_id: UUID
    upto_idx: int | None = Field(default=None, ge=0)
    expected: str | None = Field(default=None, max_length=20_000)


class EditCase(Body):
    name: str | None = Field(default=None, max_length=200)
    input: CaseInput | None = None
    expected: str | None = Field(default=None, max_length=20_000)


class Output(Body):
    case_id: UUID | None = None
    case_name: str | None = None
    output: str = Field(max_length=200_000)
    trace_id: UUID | None = None


class Run(Body):
    label: str = Field(default="", max_length=120)
    outputs: list[Output] = Field(min_length=1, max_length=2_000)
    baseline_run_id: UUID | None = None


def _scorers(items: list[Scorer] | None) -> list[dict] | None:
    return None if items is None else [s.model_dump(mode="json", exclude_none=True) for s in items]


async def checked(coro):
    try:
        return await coro
    except service.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
async def list_sets(user: dict = Depends(get_current_user)):
    return {"test_sets": await service.list_sets(user["id"])}


@router.post("", status_code=201)
async def create_set(body: CreateSet, user: dict = Depends(get_current_user)):
    return await checked(
        service.create_set(
            user["id"], body.name, body.description, _scorers(body.scorers), body.max_regressions
        )
    )


@router.get("/resolve/{ref}")
async def resolve(ref: str, user: dict = Depends(get_current_user)):
    found = await checked(service.resolve(user["id"], ref))
    return await checked(service.get_set(user["id"], found["id"]))


@router.get("/runs/{run_id}")
async def get_run(run_id: UUID, user: dict = Depends(get_current_user)):
    return await checked(service.get_run(user["id"], run_id))


@router.get("/{set_id}")
async def get_set(set_id: UUID, user: dict = Depends(get_current_user)):
    return await checked(service.get_set(user["id"], set_id))


@router.patch("/{set_id}")
async def edit_set(set_id: UUID, body: EditSet, user: dict = Depends(get_current_user)):
    changes = body.model_dump(exclude_unset=True)
    if "scorers" in changes:
        changes["scorers"] = _scorers(body.scorers)
    return await checked(service.update_set(user["id"], set_id, changes))


@router.delete("/{set_id}", status_code=204)
async def delete_set(set_id: UUID, user: dict = Depends(get_current_user)):
    await checked(service.delete_set(user["id"], set_id))


@router.post("/{set_id}/cases", status_code=201)
async def add_cases(set_id: UUID, body: Cases, user: dict = Depends(get_current_user)):
    return {
        "cases": await checked(
            service.add_cases(user["id"], set_id, [c.model_dump() for c in body.cases])
        )
    }


@router.post("/{set_id}/cases/from-trace", status_code=201)
async def case_from_trace(set_id: UUID, body: FromTrace, user: dict = Depends(get_current_user)):
    return await checked(
        service.case_from_trace(user["id"], set_id, body.trace_id, body.upto_idx, body.expected)
    )


@router.patch("/{set_id}/cases/{case_id}")
async def edit_case(
    set_id: UUID, case_id: UUID, body: EditCase, user: dict = Depends(get_current_user)
):
    return await checked(
        service.update_case(user["id"], set_id, case_id, body.model_dump(exclude_unset=True))
    )


@router.delete("/{set_id}/cases/{case_id}", status_code=204)
async def delete_case(set_id: UUID, case_id: UUID, user: dict = Depends(get_current_user)):
    await checked(service.delete_case(user["id"], set_id, case_id))


@router.post("/{set_id}/runs", status_code=202)
async def start_run(set_id: UUID, body: Run, user: dict = Depends(get_current_user)):
    outputs = [o.model_dump(mode="json") for o in body.outputs]
    return await checked(
        service.start_run(user["id"], set_id, body.label, outputs, body.baseline_run_id)
    )
