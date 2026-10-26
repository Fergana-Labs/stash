"""Evals API: examples marked good or bad in, one scoring endpoint out.

POST /api/v1/evals/{id}/score
  JSON:      {"trace": [...] | "text", "output": {"text": "...", "images": ["<base64 or data URL>"]},
              "caller": "...", "ref": "...", "metadata": {...}}
  multipart: trace (JSON or text), text, caller, ref, files (images, PDFs, text files)
-> {"call_id", "score" (0-1), "traits": [{"trait", "score" (0-1), "why"}],
    "explanation", "fixes": [{"issue", "fix"}], "keep"}

The channel (GET/POST /api/v1/evals/{id}/messages) is where people drop examples and say
what they think; the rubric (GET/PUT /api/v1/evals/{id}/rubric) is every version the eval
has had, edited by builds as evidence arrives and by the person directly.
"""

import base64
import binascii
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile as FormFile

from ..auth import get_current_user
from ..services.evals import channel, judge, service
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/evals", tags=["evals"], dependencies=[Depends(require_reward_models)]
)
User = Annotated[dict, Depends(get_current_user)]
MAX_UPLOAD_FILES = 50


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateEval(Body):
    name: str = Field(default="", max_length=160)
    instructions: str = Field(default="", max_length=2000)


class EditEval(Body):
    name: str | None = Field(default=None, max_length=160)
    instructions: str | None = Field(default=None, max_length=2000)


class Output(Body):
    text: str = Field(default="", max_length=200_000)
    images: list[str] = Field(default_factory=list, max_length=20)


class ScoreJson(Body):
    trace: list | str | None = None
    output: Output = Field(default_factory=Output)
    caller: str = Field(default="", max_length=100)
    ref: str | None = Field(default=None, max_length=200)
    metadata: dict = Field(default_factory=dict)


class LabelCall(Body):
    label: Literal["good", "bad"] | None
    note: str = Field(default="", max_length=2000)


class EditExample(Body):
    label: Literal["good", "bad"] | None
    note: str | None = Field(default=None, max_length=2000)


class Trait(Body):
    name: str = Field(min_length=1, max_length=60)
    good: str = Field(default="", max_length=400)
    bad: str = Field(default="", max_length=400)
    basis: str = Field(default="", max_length=300)


class EditRubric(Body):
    traits: list[Trait] = Field(min_length=1, max_length=10)
    base: int = Field(ge=0, description="The version the edit was made on")


async def checked(coro):
    try:
        return await coro
    except service.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except judge.JudgeUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:  # includes items.Unreadable: a file the judge can't read
        raise HTTPException(422, str(exc)) from exc


def _decode_image(value: str, index: int) -> tuple[str, bytes, str]:
    header, _, data = value.partition(",") if value.startswith("data:") else ("", "", value)
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, f"output.images[{index}] is not base64") from exc
    content_type = header[5:].split(";")[0] if header else "image/png"
    return f"image-{index + 1}", raw, content_type


async def _uploads(files: list[UploadFile]) -> list[tuple[str, bytes, str]]:
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(422, f"At most {MAX_UPLOAD_FILES} files per request")
    return [(f.filename or "file", await f.read(), f.content_type or "") for f in files]


def _file_response(data: bytes, content_type: str, name: str) -> Response:
    return Response(
        data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{name.replace(chr(34), "")}"',
        },
    )


@router.get("")
async def list_evals(user: User):
    return {"evals": await service.list_evals(user["id"])}


@router.post("", status_code=201)
async def create_eval(body: CreateEval, user: User):
    return await service.create(user["id"], body.name, body.instructions)


@router.get("/{eval_id}")
async def get_eval(eval_id: UUID, user: User):
    return await checked(service.get(user["id"], eval_id))


@router.patch("/{eval_id}")
async def edit_eval(eval_id: UUID, body: EditEval, user: User):
    return await checked(service.update(user["id"], eval_id, body.name, body.instructions))


@router.delete("/{eval_id}", status_code=204)
async def delete_eval(eval_id: UUID, user: User):
    await checked(service.delete(user["id"], eval_id))


@router.get("/{eval_id}/examples")
async def list_examples(eval_id: UUID, user: User):
    return {"examples": await checked(service.list_examples(user["id"], eval_id))}


@router.post("/{eval_id}/examples", status_code=201)
async def add_examples(
    eval_id: UUID,
    user: User,
    label: Annotated[Literal["good", "bad"], Form()],
    note: Annotated[str, Form(max_length=2000)] = "",
    text: Annotated[str, Form(max_length=200_000)] = "",
    trace: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006
):
    """Each file becomes one example; without files, the text and/or trace is one example."""
    parsed_trace = _trace_field(trace)
    created = await checked(
        service.add_examples(
            user["id"],
            eval_id,
            label,
            await _uploads(files),
            text=text,
            trace=parsed_trace,
            note=note,
        )
    )
    return {"examples": created}


def _trace_field(value: str):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@router.patch("/{eval_id}/examples/{example_id}")
async def edit_example(eval_id: UUID, example_id: UUID, body: EditExample, user: User):
    return await checked(
        service.edit_example(user["id"], eval_id, example_id, body.label, body.note)
    )


@router.delete("/{eval_id}/examples/{example_id}", status_code=204)
async def delete_example(eval_id: UUID, example_id: UUID, user: User):
    await checked(service.delete_example(user["id"], eval_id, example_id))


@router.get("/{eval_id}/examples/{example_id}/files/{index}")
async def example_file(eval_id: UUID, example_id: UUID, index: int, user: User):
    return _file_response(
        *await checked(service.example_file(user["id"], eval_id, example_id, index))
    )


@router.post("/{eval_id}/build", status_code=202)
async def build(eval_id: UUID, user: User, fresh: bool = False):
    """Bring the rubric up to date now; fresh rewrites it from scratch."""
    return await checked(service.start_build(user["id"], eval_id, fresh))


@router.get("/{eval_id}/rubric")
async def rubric(eval_id: UUID, user: User):
    return await checked(service.rubric(user["id"], eval_id))


@router.put("/{eval_id}/rubric")
async def edit_rubric(eval_id: UUID, body: EditRubric, user: User):
    traits = [t.model_dump(exclude_defaults=False) for t in body.traits]
    if len({t["name"].strip().lower() for t in traits}) < len(traits):
        raise HTTPException(422, "Trait names must be unique")
    return await checked(service.edit_rubric(user["id"], eval_id, traits, body.base))


@router.get("/{eval_id}/messages")
async def messages(eval_id: UUID, user: User):
    return await checked(channel.listing(user["id"], eval_id))


@router.post("/{eval_id}/messages", status_code=201)
async def post_message(
    eval_id: UUID,
    user: User,
    text: Annotated[str, Form(max_length=channel.MAX_TEXT)] = "",
    thread_id: Annotated[UUID | None, Form()] = None,
    more: Annotated[bool, Form()] = False,
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006
):
    """Post to the eval's channel. Each file becomes an example the channel agent labels from
    what the person says; files that can't be read come back in "skipped". A drop bigger than
    one request posts with more=true, then sends the rest to .../messages/{id}/files."""
    return await checked(
        channel.post(
            user["id"], eval_id, text, await _uploads(files), thread_id=thread_id, more=more
        )
    )


@router.post("/{eval_id}/messages/{message_id}/files", status_code=201)
async def attach_files(
    eval_id: UUID,
    message_id: UUID,
    user: User,
    more: Annotated[bool, Form()] = False,
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006
):
    return await checked(
        channel.attach(user["id"], eval_id, message_id, await _uploads(files), more)
    )


@router.post("/{eval_id}/score")
async def score(eval_id: UUID, request: Request, user: User):
    """Score an agent's output. JSON or multipart; see the module docstring."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        # request.form() yields Starlette's UploadFile, which FastAPI's subclass isn't.
        uploads = [
            f for f in form.getlist("files") + form.getlist("file") if isinstance(f, FormFile)
        ]
        return await checked(
            service.score(
                user["id"],
                eval_id,
                trace=_trace_field(str(form.get("trace") or "")),
                text=str(form.get("text") or ""),
                files=await _uploads(uploads),
                caller=str(form.get("caller") or "")[:100],
                ref=str(form.get("ref")) if form.get("ref") else None,
            )
        )
    try:
        body = ScoreJson.model_validate(await request.json())
    except Exception as exc:
        raise HTTPException(
            422, f"Send JSON matching the score request, or multipart: {exc}"
        ) from exc
    images = [_decode_image(v, i) for i, v in enumerate(body.output.images)]
    return await checked(
        service.score(
            user["id"],
            eval_id,
            trace=body.trace,
            text=body.output.text,
            files=images,
            caller=body.caller,
            ref=body.ref,
            metadata=body.metadata,
        )
    )


@router.get("/{eval_id}/calls")
async def list_calls(eval_id: UUID, user: User, limit: int = 100):
    return {
        "calls": await checked(service.list_calls(user["id"], eval_id, min(max(limit, 1), 500)))
    }


@router.get("/{eval_id}/calls/{call_id}/files/{index}")
async def call_file(eval_id: UUID, call_id: UUID, index: int, user: User):
    return _file_response(*await checked(service.call_file(user["id"], eval_id, call_id, index)))


@router.put("/{eval_id}/calls/{call_id}/label")
async def label_call(eval_id: UUID, call_id: UUID, body: LabelCall, user: User):
    return await checked(service.label_call(user["id"], eval_id, call_id, body.label, body.note))
