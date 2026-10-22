"""Image evals API: upload liked/disliked examples, train, score images, review calls.

Every route is owner-scoped; another owner's id is a 404. Agents call
POST /{id}/score with an API key (read-only keys are allowed) and get a score
plus written fixes; every call is kept for the owner to review and label.
"""

import base64
import binascii
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user
from ..services.image_eval import embedder, interview, service
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/image-evals",
    tags=["image-evals"],
    dependencies=[Depends(require_reward_models)],
)
User = Annotated[dict, Depends(get_current_user)]
MAX_UPLOAD_FILES = 100


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateClassifier(Body):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class EditClassifier(Body):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)


class ScoreJson(Body):
    image_base64: str
    caller: str = Field(default="", max_length=100)
    task: str = Field(default="", max_length=500)
    comments: bool = True


class Answer(Body):
    question: str = Field(max_length=300)
    answer: str = Field(max_length=1000)


class Answers(Body):
    answers: list[Answer] = Field(default_factory=list, max_length=8)
    leave_out: list[UUID] = Field(default_factory=list, max_length=200)
    skipped: bool = False


class LabelCall(Body):
    label: Literal["liked", "disliked"] | None
    note: str = Field(default="", max_length=2000)


async def checked(coro):
    try:
        return await coro
    except service.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (service.StorageUnavailable, embedder.EmbedderUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _image_response(data: bytes, content_type: str) -> Response:
    return Response(
        data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.get("")
async def list_classifiers(user: User):
    return {"classifiers": await service.list_classifiers(user["id"])}


@router.post("", status_code=201)
async def create_classifier(body: CreateClassifier, user: User):
    return await service.create(user["id"], body.name, body.description)


@router.get("/by-model/{model_id}")
async def get_by_model(model_id: UUID, user: User):
    """The image eval behind a wizard-made eval; 404 when the eval is another kind."""
    found = await service.by_model(user["id"], model_id)
    if found is None:
        raise HTTPException(404, "Not an image eval")
    return found


@router.get("/{classifier_id}")
async def get_classifier(classifier_id: UUID, user: User):
    return await checked(service.get(user["id"], classifier_id))


@router.patch("/{classifier_id}")
async def edit_classifier(classifier_id: UUID, body: EditClassifier, user: User):
    return await checked(service.rename(user["id"], classifier_id, body.name, body.description))


@router.delete("/{classifier_id}", status_code=204)
async def delete_classifier(classifier_id: UUID, user: User) -> None:
    await checked(service.delete(user["id"], classifier_id))


@router.get("/{classifier_id}/examples")
async def list_examples(classifier_id: UUID, user: User):
    return {"examples": await checked(service.list_examples(user["id"], classifier_id))}


@router.post("/{classifier_id}/examples", status_code=201)
async def add_examples(
    classifier_id: UUID,
    user: User,
    label: Annotated[Literal["liked", "disliked"], Form()],
    files: Annotated[list[UploadFile], File()],
):
    if not files or len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(422, f"Upload between 1 and {MAX_UPLOAD_FILES} images at a time")
    payload = [(f.filename or "", await f.read(), f.content_type or "") for f in files]
    return {
        "examples": await checked(service.add_examples(user["id"], classifier_id, label, payload))
    }


@router.delete("/{classifier_id}/examples/{example_id}", status_code=204)
async def delete_example(classifier_id: UUID, example_id: UUID, user: User) -> None:
    await checked(service.delete_example(user["id"], classifier_id, example_id))


@router.get("/{classifier_id}/examples/{example_id}/image")
async def example_image(classifier_id: UUID, example_id: UUID, user: User):
    return _image_response(
        *await checked(service.example_image(user["id"], classifier_id, example_id))
    )


@router.post("/{classifier_id}/interview")
async def ask(classifier_id: UUID, user: User):
    """The questions Claude asks after looking at the examples (written once, then kept)."""
    return await checked(interview.questions(user["id"], classifier_id))


@router.put("/{classifier_id}/interview")
async def answer(classifier_id: UUID, body: Answers, user: User):
    return await checked(
        interview.answer(
            user["id"],
            classifier_id,
            [a.model_dump() for a in body.answers],
            body.leave_out,
            body.skipped,
        )
    )


@router.post("/{classifier_id}/build", status_code=202)
async def build(classifier_id: UUID, user: User):
    """One-step build: write a style brief, add imitations as disliked examples, train."""
    return await checked(service.start_build(user["id"], classifier_id))


@router.post("/{classifier_id}/train")
async def train(classifier_id: UUID, user: User):
    return await checked(service.train(user["id"], classifier_id))


@router.post("/{classifier_id}/score")
async def score(classifier_id: UUID, request: Request, user: User):
    """Score one image. Multipart: file (+ caller, task, comments); or JSON {image_base64, ...}."""
    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise HTTPException(422, "Send the image as the multipart field 'file'")
        data, filename, ctype = (
            await upload.read(),
            upload.filename or "",
            upload.content_type or "",
        )
        caller, task = str(form.get("caller", "")), str(form.get("task", ""))
        comments = str(form.get("comments", "true")).lower() not in ("false", "0", "no")
    else:
        try:
            body = ScoreJson.model_validate(await request.json())
            data = base64.b64decode(body.image_base64.split(",")[-1], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(
                422, "Send JSON {image_base64, caller?, task?, comments?} or a multipart file"
            ) from exc
        filename, ctype, caller, task, comments = "", "", body.caller, body.task, body.comments
    return await checked(
        service.score(
            user["id"],
            classifier_id,
            data,
            ctype,
            caller=caller[:100] or user.get("name", ""),
            task=task[:500],
            comments=comments,
            filename=filename,
        )
    )


@router.get("/{classifier_id}/calls")
async def list_calls(classifier_id: UUID, user: User, limit: int = 100):
    return {
        "calls": await checked(
            service.list_calls(user["id"], classifier_id, max(1, min(limit, 500)))
        )
    }


@router.get("/{classifier_id}/calls/{call_id}/image")
async def call_image(classifier_id: UUID, call_id: UUID, user: User):
    return _image_response(*await checked(service.call_image(user["id"], classifier_id, call_id)))


@router.put("/{classifier_id}/calls/{call_id}/label")
async def label_call(classifier_id: UUID, call_id: UUID, body: LabelCall, user: User):
    return await checked(
        service.label_call(user["id"], classifier_id, call_id, body.label, body.note)
    )
