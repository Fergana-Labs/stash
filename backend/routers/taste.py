"""The owner-scoped taste workflow and its runtime oracle."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth import get_current_user
from ..services import taste
from ..services.intuition.service import Conflict, NotFound
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/taste", tags=["taste"], dependencies=[Depends(require_reward_models)]
)
User = Annotated[dict, Depends(get_current_user)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Review(Body):
    label: Literal["liked", "disliked", "skip"]
    note: str = Field(default="", max_length=2000)


class Reset(Body):
    session_id: UUID


class TraceFile(Body):
    name: str = Field(max_length=200)
    content: str = Field(min_length=1, max_length=40_000_000)


MAX_UPLOAD_CHARS = 80_000_000


class TraceUpload(Body):
    session_id: UUID
    # A dropped Claude Code or Codex history folder holds many session files.
    files: list[TraceFile] = Field(min_length=1, max_length=200)

    @field_validator("files")
    @classmethod
    def bounded_total(cls, files: list[TraceFile]) -> list[TraceFile]:
        if sum(len(f.content) for f in files) > MAX_UPLOAD_CHARS:
            raise ValueError("Upload at most 80 MB of traces at once.")
        return files


class Source(Body):
    kind: Literal["local", "session", "trace"]
    id: str = Field(min_length=1, max_length=128)


class Job(Body):
    operation: Literal[
        "discover",
        "collect",
        "collect_all",
        "extract_labels",
        "build",
        "skill",
        "gepa",
        "weights",
        "evaluate",
    ]
    query: str = Field(default="website", max_length=200)
    history_source: Literal["all", "recorded", "local"] = "all"
    event_offset: int = Field(default=0, ge=0, le=1000000)
    source: Source | None = None
    offset: int = Field(default=0, ge=0, le=100000)
    asset_offset: int = Field(default=0, ge=0, le=100000)


class Step(Body):
    id: str = Field(max_length=100)
    role: Literal["user", "assistant", "tool"]
    text: str = Field(max_length=2400)


class Prediction(Body):
    brief: str = Field(min_length=1, max_length=4000)
    trace: list[Step] = Field(min_length=1, max_length=40)
    trace_complete: bool = False
    html: str = Field(default="", max_length=8000)
    screenshot_base64: str = Field(min_length=1, max_length=5400000)
    ref: str | None = Field(default=None, max_length=200)


async def checked(coro):
    try:
        return await coro
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
async def get(user: User):
    try:
        return await taste.detail(user["id"])
    except NotFound:
        return None


@router.post("")
async def create(user: User):
    await taste.workspace(user["id"], create=True)
    return await taste.detail(user["id"])


@router.patch("/examples/{identity}")
async def review(identity: str, req: Review, user: User):
    return await checked(taste.review(user["id"], identity, req.label, req.note))


@router.post("/reset")
async def reset(req: Reset, user: User):
    return await checked(taste.reset_demo(user["id"], req.session_id))


@router.post("/traces")
async def traces(req: TraceUpload, user: User):
    return await checked(
        taste.upload_traces(user["id"], req.session_id, [f.model_dump() for f in req.files])
    )


@router.get("/images/{kind}/{identity}")
async def image(kind: Literal["example", "design", "check"], identity: str, user: User):
    import base64

    row = await checked(taste.workspace(user["id"]))
    try:
        path = taste.image_path(row, kind, identity)
        raw = path.read_bytes()
        if len(raw) > 8_000_000:
            raise ValueError("Image exceeds preview limit")
        mime = "image/jpeg" if raw.startswith(b"\xff\xd8\xff") else "image/png"
        return {"data_url": f"data:{mime};base64," + base64.b64encode(raw).decode()}
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/inspect/{kind}/{identity}")
async def inspect(kind: Literal["example", "design"], identity: str, user: User):
    return await checked(taste.inspect(user["id"], kind, identity))


@router.post("/jobs", status_code=202)
async def start(req: Job, user: User):
    if req.operation == "collect" and not req.source:
        raise HTTPException(422, "Select a history session first")
    return await checked(
        taste.enqueue(user["id"], req.operation, req.model_dump(mode="json", exclude_none=True))
    )


class ExampleFile(Body):
    name: str = Field(max_length=200)
    label: Literal["liked", "disliked"]
    # Base64 image bytes, or HTML text for .html files. Empty when `url` is given.
    content: str = Field(default="", max_length=12_000_000)
    url: str | None = Field(default=None, max_length=2000)


class ExampleUpload(Body):
    session_id: UUID
    files: list[ExampleFile] = Field(min_length=1, max_length=40)


@router.post("/examples")
async def examples(req: ExampleUpload, user: User):
    return await checked(
        taste.add_examples(user["id"], req.session_id, [f.model_dump() for f in req.files])
    )


class HillClimb(Body):
    brief: str = Field(min_length=1, max_length=4000)


@router.post("/hillclimb")
async def hillclimb(req: HillClimb, user: User):
    return await checked(taste.start_hillclimb(user["id"], req.brief))


@router.get("/hillclimb/{job_id}")
async def hillclimb_state(job_id: UUID, user: User):
    return await checked(taste.hillclimb_state(user["id"], job_id))


@router.post("/predict")
async def predict(req: Prediction, user: User):
    return await checked(
        taste.predict(user["id"], req.model_dump(mode="json", exclude={"ref"}), ref=req.ref)
    )


class Comparison(Body):
    a: str = Field(pattern="^[a-f0-9]{64}$")
    b: str = Field(pattern="^[a-f0-9]{64}$")
    winner: str = Field(max_length=64)


@router.post("/comparisons")
async def compare(req: Comparison, user: User):
    return await checked(taste.compare(user["id"], req.a, req.b, req.winner))


@router.post("/check-design/{identity}")
async def check_design(identity: str, user: User):
    return await checked(taste.check_design(user["id"], identity))


@router.get("/checks/{identity}")
async def checkpoint(identity: str, user: User):
    from uuid import UUID

    try:
        key = UUID(identity)
    except ValueError as exc:
        raise HTTPException(404, "Checkpoint not found") from exc
    return await checked(taste.checkpoint(user["id"], key))


@router.post("/resume-wizard")
async def resume(user: User):
    return await checked(taste.bind_wizard(user["id"]))
