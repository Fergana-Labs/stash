"""Reward model platform API: traces, annotations, exports, reward models, GEPA, SQL.

Contract: docs/reward-models/DESIGN.md ("REST API"). Every row is private to
its owner; another owner's id is a 404, never a 403, so ids don't leak.
"""

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..database import get_pool
from ..services.rm import annotations, datasets, query, traces
from ..services.rm.adapters import TraceFormatError, list_formats
from ..tasks import reward_models as rm_tasks

router = APIRouter(prefix="/api/v1/rm", tags=["reward-models"])

DEFAULT_BASE_MODEL = "Qwen/Qwen3-0.6B"
DEFAULT_EPOCHS = 1
DEFAULT_MAX_METRIC_CALLS = 150


class ImportRequest(BaseModel):
    format: str
    data: str


class Quote(BaseModel):
    text: str = Field(min_length=1)
    prefix: str
    suffix: str


class CreateAnnotationRequest(BaseModel):
    step_id: UUID | None = None
    rating: Literal[1, -1] | None = None
    comment: str | None = None
    quote: Quote | None = None


class UpdateAnnotationRequest(BaseModel):
    rating: Literal[1, -1] | None = None
    comment: str | None = None
    label_error: bool | None = None
    label_error_note: str | None = None


class CreateRewardModelRequest(BaseModel):
    name: str = Field(min_length=1)
    base_model: str = DEFAULT_BASE_MODEL
    compute: Literal["local", "modal"]
    epochs: int = Field(default=DEFAULT_EPOCHS, ge=1)
    max_pairs: int = Field(default=datasets.DEFAULT_MAX_PAIRS, ge=1)


class CreateGepaRunRequest(BaseModel):
    reward_model_id: UUID
    seed_prompt: str = Field(min_length=1)
    task_model: str = Field(min_length=1)
    task_api_base: str | None = None
    reflection_model: str = Field(min_length=1)
    max_metric_calls: int = Field(default=DEFAULT_MAX_METRIC_CALLS, ge=1)


class QueryRequest(BaseModel):
    sql: str


def _ndjson(lines: list[dict]) -> Response:
    body = "".join(json.dumps(line) + "\n" for line in lines)
    return Response(content=body, media_type="application/x-ndjson")


# ── Traces ────────────────────────────────────────────────────────────────


@router.get("/formats")
async def get_formats(current_user: dict = Depends(get_current_user)) -> list[dict]:
    return list_formats()


@router.post("/traces/import")
async def import_traces(req: ImportRequest, current_user: dict = Depends(get_current_user)) -> dict:
    try:
        return await traces.import_traces(current_user["id"], req.format, req.data)
    except TraceFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/traces")
async def list_traces(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return await traces.list_traces(current_user["id"], limit, offset)


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    trace = await traces.get_trace(current_user["id"], trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@router.delete("/traces/{trace_id}", status_code=204)
async def delete_trace(trace_id: UUID, current_user: dict = Depends(get_current_user)) -> None:
    if not await traces.delete_trace(current_user["id"], trace_id):
        raise HTTPException(status_code=404, detail="Trace not found")


# ── Annotations ───────────────────────────────────────────────────────────


@router.post("/traces/{trace_id}/annotations")
async def create_annotation(
    trace_id: UUID,
    req: CreateAnnotationRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    quote = req.quote.model_dump() if req.quote else None
    try:
        annotation = await annotations.create(
            current_user["id"], trace_id, req.step_id, req.rating, req.comment, quote
        )
    except annotations.AnnotationInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if annotation is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return annotation


@router.patch("/annotations/{annotation_id}")
async def update_annotation(
    annotation_id: UUID,
    req: UpdateAnnotationRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        annotation = await annotations.update(
            current_user["id"], annotation_id, req.model_dump(exclude_unset=True)
        )
    except annotations.AnnotationInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return annotation


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: UUID, current_user: dict = Depends(get_current_user)
) -> None:
    if not await annotations.delete(current_user["id"], annotation_id):
        raise HTTPException(status_code=404, detail="Annotation not found")


# ── Exports ───────────────────────────────────────────────────────────────


@router.get("/export/traces")
async def export_traces(current_user: dict = Depends(get_current_user)) -> Response:
    return _ndjson(await traces.export_traces(current_user["id"]))


@router.get("/export/annotations")
async def export_annotations(current_user: dict = Depends(get_current_user)) -> Response:
    return _ndjson(await annotations.export_annotations(current_user["id"]))


@router.get("/export/pairs")
async def export_pairs(current_user: dict = Depends(get_current_user)) -> Response:
    return _ndjson(await datasets.build_pairs(current_user["id"]))


# ── Reward models ─────────────────────────────────────────────────────────


@router.post("/reward-models")
async def create_reward_model(
    req: CreateRewardModelRequest, current_user: dict = Depends(get_current_user)
) -> dict:
    # Checked again when the job runs: labels can change while it is queued.
    try:
        datasets.check_enough_pairs(await datasets.build_pairs(current_user["id"], req.max_pairs))
    except datasets.NotEnoughPairs as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = await get_pool().fetchrow(
        """
        INSERT INTO rm_reward_models (owner_user_id, name, base_model, compute, epochs, max_pairs)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        current_user["id"],
        req.name,
        req.base_model,
        req.compute,
        req.epochs,
        req.max_pairs,
    )
    rm_tasks.train_reward_model.delay(str(row["id"]))
    return _reward_model(row)


@router.get("/reward-models")
async def list_reward_models(current_user: dict = Depends(get_current_user)) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT * FROM rm_reward_models WHERE owner_user_id = $1 ORDER BY created_at DESC",
        current_user["id"],
    )
    return [_reward_model(row) for row in rows]


@router.get("/reward-models/{model_id}")
async def get_reward_model(model_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM rm_reward_models WHERE owner_user_id = $1 AND id = $2",
        current_user["id"],
        model_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Reward model not found")
    return _reward_model(row)


def _reward_model(row) -> dict:
    return {
        key: row[key]
        for key in (
            "id",
            "name",
            "base_model",
            "compute",
            "epochs",
            "max_pairs",
            "status",
            "num_pairs",
            "metrics",
            "error",
            "created_at",
            "started_at",
            "finished_at",
        )
    }


# ── GEPA runs ─────────────────────────────────────────────────────────────


@router.post("/gepa-runs")
async def create_gepa_run(
    req: CreateGepaRunRequest, current_user: dict = Depends(get_current_user)
) -> dict:
    pool = get_pool()
    model_status = await pool.fetchval(
        "SELECT status FROM rm_reward_models WHERE owner_user_id = $1 AND id = $2",
        current_user["id"],
        req.reward_model_id,
    )
    if model_status is None:
        raise HTTPException(status_code=404, detail="Reward model not found")
    if model_status != "succeeded":
        raise HTTPException(status_code=422, detail="Reward model has not finished training")

    row = await pool.fetchrow(
        """
        INSERT INTO rm_gepa_runs (owner_user_id, reward_model_id, seed_prompt, task_model,
                                  task_api_base, reflection_model, max_metric_calls)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        current_user["id"],
        req.reward_model_id,
        req.seed_prompt,
        req.task_model,
        req.task_api_base,
        req.reflection_model,
        req.max_metric_calls,
    )
    rm_tasks.run_gepa.delay(str(row["id"]))
    return _gepa_run(row)


@router.get("/gepa-runs")
async def list_gepa_runs(current_user: dict = Depends(get_current_user)) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT * FROM rm_gepa_runs WHERE owner_user_id = $1 ORDER BY created_at DESC",
        current_user["id"],
    )
    return [_gepa_run(row) for row in rows]


@router.get("/gepa-runs/{run_id}")
async def get_gepa_run(run_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM rm_gepa_runs WHERE owner_user_id = $1 AND id = $2",
        current_user["id"],
        run_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="GEPA run not found")
    return _gepa_run(row)


def _gepa_run(row) -> dict:
    run = dict(row)
    del run["owner_user_id"]
    return run


# ── SQL ───────────────────────────────────────────────────────────────────


@router.post("/query")
async def run_query(req: QueryRequest, current_user: dict = Depends(get_current_user)) -> dict:
    try:
        return await query.run_query(current_user["id"], req.sql)
    except query.QueryRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
