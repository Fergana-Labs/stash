"""The Models page's endpoints. Deliberately outside the OpenAPI schema and
the agent docs: agents reach models through the MCP server a skill
declares, and nothing here is part of the public API.

Payment surfaces as 402 with the checkout URL in the body, which is what the
page opens."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user, get_scope
from . import registry, service

router = APIRouter(prefix="/api/v1/me/models", tags=["trained-models"], include_in_schema=False)


class CorpusCheckRequest(BaseModel):
    kind: str
    folder: str = Field(min_length=1)


class TrainRequest(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=40)
    folder: str = Field(min_length=1)


class RunRequest(BaseModel):
    op: str
    input: dict = Field(default_factory=dict)


def _kind(kind: str) -> None:
    try:
        registry.get(kind)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("")
async def list_models(
    current_user: dict = Depends(get_current_user),
    owner_user_id: UUID = Depends(get_scope),
) -> list[dict]:
    return [service.public(m) for m in await service.list_models(owner_user_id)]


@router.get("/kinds")
async def list_kinds(current_user: dict = Depends(get_current_user)) -> list[dict]:
    return [
        {"kind": name, "title": module.TITLE, "base_model": module.BASE_MODEL}
        for name, module in registry.KINDS.items()
    ]


@router.get("/setup-status/{kind}")
async def setup_status(
    kind: str,
    current_user: dict = Depends(get_current_user),
    owner_user_id: UUID = Depends(get_scope),
) -> dict:
    _kind(kind)
    return await service.setup_status(owner_user_id, current_user, kind)


@router.post("/check-corpus")
async def check_corpus(
    req: CorpusCheckRequest,
    current_user: dict = Depends(get_current_user),
    owner_user_id: UUID = Depends(get_scope),
) -> dict:
    _kind(req.kind)
    try:
        report, folder = await service.check_corpus(
            owner_user_id, current_user["id"], req.kind, req.folder
        )
    except (service.FolderNotFound, service.AmbiguousFolder) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"folder": {"id": str(folder["id"]), "name": folder["name"]}, **report.to_dict()}


@router.post("", status_code=201)
async def train(
    req: TrainRequest,
    current_user: dict = Depends(get_current_user),
    owner_user_id: UUID = Depends(get_scope),
) -> dict:
    _kind(req.kind)
    try:
        model = await service.train(owner_user_id, current_user, req.kind, req.name, req.folder)
    except service.PaymentRequired as error:
        raise HTTPException(
            status_code=402,
            detail={
                "message": f"Training costs ${error.amount_cents // 100}. Pay, then train again.",
                "checkout_url": error.checkout_url,
            },
        ) from error
    except service.CorpusNotReady as error:
        raise HTTPException(status_code=422, detail=error.report.to_dict()) from error
    except (service.FolderNotFound, service.AmbiguousFolder) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except service.NameTaken as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except service.BadName as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return service.public(model)


@router.get("/{kind}/{name}")
async def get_model(
    kind: str,
    name: str,
    current_user: dict = Depends(get_current_user),
    owner_user_id: UUID = Depends(get_scope),
) -> dict:
    _kind(kind)
    try:
        return service.public(await service.get_model(owner_user_id, kind, name))
    except service.ModelNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{kind}/{name}/run")
async def run(
    kind: str,
    name: str,
    req: RunRequest,
    current_user: dict = Depends(get_current_user),
    owner_user_id: UUID = Depends(get_scope),
) -> dict:
    _kind(kind)
    try:
        return await service.run(owner_user_id, kind, name, req.op, req.input)
    except service.ModelNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except service.ModelNotReady as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{kind}/{name}/jobs/{job_id}")
async def job_result(
    kind: str,
    name: str,
    job_id: str,
    current_user: dict = Depends(get_current_user),
    owner_user_id: UUID = Depends(get_scope),
) -> dict:
    _kind(kind)
    try:
        return await service.job_result(owner_user_id, kind, name, job_id)
    except service.ModelNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{kind}/{name}", status_code=204)
async def delete_model(
    kind: str,
    name: str,
    current_user: dict = Depends(get_current_user),
    owner_user_id: UUID = Depends(get_scope),
) -> None:
    _kind(kind)
    if not await service.delete_model(owner_user_id, kind, name):
        raise HTTPException(status_code=404, detail=f"no {kind} model named {name!r}")
