"""Intuition models API: author, train, evaluate, promote and serve personal judges.

Every route is owner-scoped; another owner's id is a 404. Draft routes edit
the single draft version (creating it from the active version when needed);
serving routes use the active version unless `version="draft"` is requested.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user
from ..services.intuition import (
    builder,
    demo,
    drop_folder,
    feedback,
    improve,
    mining,
    monitoring,
    providers,
    rubric_builder,
    runs,
    selection,
    service,
)
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/intuitions",
    tags=["intuitions"],
    dependencies=[Depends(require_reward_models)],
)

Item = str | dict
Source = Literal["human", "agent", "generated", "production"]
Which = Literal["active", "draft"]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateModel(Body):
    name: str = Field(min_length=1, max_length=160)
    output_type: Literal["choice", "preference", "multi"]
    description: str = Field(default="", max_length=6000)
    labels: list[dict] = Field(default_factory=list)
    rubric: list[dict] = Field(default_factory=list)


class Rename(Body):
    name: str = Field(min_length=1, max_length=160)


class EditDraft(Body):
    description: str | None = Field(default=None, max_length=6000)
    labels: list[dict] | None = None
    rubric: list[dict] | None = None
    seed_example_ids: list[str] | None = None
    provider: Literal["jev", "agent_judge"] | None = None


class Grade(Body):
    limit: int = Field(default=service.GRADE_BATCH, ge=1, le=50)


class Fit(Body):
    l2: float = Field(default=service.DEFAULT_L2, ge=0, le=100)
    train_on: Literal["train", "all"] = "train"
    sources: list[Source] | None = None
    calibrate: bool = True


class Head(Body):
    weights: list[list[float]]
    bias: list[float]
    temperature: float = 1.0


class Promote(Body):
    force: bool = False


class NewExample(Body):
    item: Item
    item_b: Item | None = None
    label: str | None = None
    split: Literal["train", "eval"] | None = None
    needs_review: bool = False
    note: str = Field(default="", max_length=2000)


class AddExamples(Body):
    examples: list[NewExample] = Field(min_length=1, max_length=500)
    source: Source = "human"


class EditExample(Body):
    label: str | None = None
    split: Literal["train", "eval"] | None = None
    needs_review: bool | None = None
    note: str | None = Field(default=None, max_length=2000)
    # Pinned examples are regression tests: a new version must keep them correct.
    pinned: bool | None = None
    calibration: bool | None = None


class Generate(Body):
    count: int = Field(default=6, ge=1, le=20)
    guidance: str = Field(default="", max_length=2000)
    # Suggest a label (and why) for each item; they still wait for a person to accept.
    propose: bool = True


class Predict(Body):
    item: Item
    version: Which = "active"
    version_id: UUID | None = None
    caller: str = Field(default="api", max_length=100)
    # Your own id for this call (ticket, message, run step); feedback can use it later.
    ref: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict = Field(default_factory=dict)
    # The task this call belongs to; report its outcome at /runs/{run}/outcome.
    run: str | None = Field(default=None, min_length=1, max_length=200)
    step: int | None = Field(default=None, ge=0)


class Compare(Body):
    item_a: Item
    item_b: Item
    version: Which = "active"
    caller: str = Field(default="api", max_length=100)
    ref: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict = Field(default_factory=dict)
    # The task this call belongs to; report its outcome at /runs/{run}/outcome.
    run: str | None = Field(default=None, min_length=1, max_length=200)
    step: int | None = Field(default=None, ge=0)


class Feedback(Body):
    prediction_id: UUID | None = None
    ref: str | None = Field(default=None, min_length=1, max_length=200)
    label: str | None = None
    value: float | None = None
    source: Literal["human", "outcome", "downstream"] = "human"
    note: str = Field(default="", max_length=2000)
    learn: bool = False


class Review(Body):
    label: str | None = None
    dismiss: bool = False
    note: str = Field(default="", max_length=2000)
    source: Source = "human"


async def checked(coro):
    try:
        return await coro
    except service.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except providers.ProviderError as exc:
        raise HTTPException(503 if not exc.retryable else 502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


User = Annotated[dict, Depends(get_current_user)]


@router.get("")
async def list_models(user: User):
    return {"models": await service.list_models(user["id"]), "judge": providers.status()}


@router.post("", status_code=201)
async def create_model(req: CreateModel, user: User):
    return await checked(service.create_model(user["id"], **req.model_dump()))


@router.post("/examples/support-replies", status_code=201)
async def load_example(user: User):
    """Create the bundled, pre-graded demo model so the UI is playable without a judge key."""
    return await checked(demo.load(user["id"]))


@router.post("/inputs")
async def read_input(file: UploadFile, user: User):
    data = await file.read(builder.MAX_BYTES + 1)
    try:
        return await checked(
            builder.read_input(
                data, file.filename or "input.txt", file.content_type or "text/plain"
            )
        )
    except TimeoutError as exc:
        raise HTTPException(422, "Document took too long to read; use a smaller file") from exc


class RunOutcome(Body):
    value: float = Field(ge=0, le=1)
    source: str = Field(default="outcome", min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)


@router.get("/runs")
async def list_runs(
    user: User, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)
):
    return await checked(runs.list_runs(user["id"], limit, offset))


@router.get("/runs/{external_id}")
async def get_run(external_id: str, user: User):
    return await checked(runs.get(user["id"], external_id))


@router.post("/runs/{external_id}/outcome")
async def run_outcome(external_id: str, req: RunOutcome, user: User):
    """Report how a task ended (0 failed … 1 succeeded); credited to the evals' calls in it."""
    return await checked(
        runs.record_outcome(user["id"], external_id, req.value, req.source, req.note)
    )


@router.post("/{model_id}/builder/examples", status_code=201)
async def builder_examples(model_id: UUID, req: AddExamples, user: User):
    # The builder owns the split; users do not need to choose this parameter.
    await checked(
        service.add_examples(
            user["id"],
            model_id,
            [
                {
                    **e.model_dump(),
                    "split": "train",
                    "needs_review": e.needs_review or e.label is None,
                }
                for e in req.examples
            ],
            req.source,
        )
    )
    return await checked(builder.reserve_holdout(user["id"], model_id))


@router.post("/{model_id}/builder/prepare")
async def prepare_builder(model_id: UUID, user: User):
    return await checked(builder.prepare(user["id"], model_id))


class TraceExample(Body):
    trace_id: UUID
    label: str
    note: str = Field(default="", max_length=2000)


@router.post("/{model_id}/builder/trace", status_code=201)
async def trace_example(model_id: UUID, req: TraceExample, user: User):
    await checked(service.get_detail(user["id"], model_id))
    item, notes = await checked(builder.trace_input(user["id"], req.trace_id))
    await checked(
        service.add_examples(
            user["id"],
            model_id,
            [
                {
                    "item": item,
                    "label": req.label,
                    "note": (req.note + "\n" + notes).strip()[:2000],
                    "split": "train",
                }
            ],
            "human",
        )
    )
    return await checked(builder.reserve_holdout(user["id"], model_id))


@router.get("/{model_id}")
async def detail(model_id: UUID, user: User):
    return await checked(service.get_detail(user["id"], model_id))


@router.patch("/{model_id}")
async def rename(model_id: UUID, req: Rename, user: User):
    return await checked(service.rename_model(user["id"], model_id, req.name))


@router.delete("/{model_id}", status_code=204)
async def delete(model_id: UUID, user: User):
    await checked(service.delete_model(user["id"], model_id))


@router.patch("/{model_id}/draft")
async def edit_draft(model_id: UUID, req: EditDraft, user: User):
    return await checked(
        service.update_draft(user["id"], model_id, req.model_dump(exclude_none=True))
    )


@router.delete("/{model_id}/draft")
async def discard_draft(model_id: UUID, user: User):
    return await checked(service.discard_draft(user["id"], model_id))


@router.post("/{model_id}/draft/grade")
async def grade(model_id: UUID, req: Grade, user: User):
    return await checked(service.grade_pending(user["id"], model_id, req.limit))


@router.post("/{model_id}/draft/fit")
async def fit(model_id: UUID, req: Fit, user: User):
    return await checked(service.fit(user["id"], model_id, **req.model_dump()))


@router.put("/{model_id}/draft/head")
async def set_head(model_id: UUID, req: Head, user: User):
    return await checked(
        service.set_head(user["id"], model_id, req.weights, req.bias, req.temperature)
    )


@router.post("/{model_id}/draft/promote")
async def promote(model_id: UUID, req: Promote, user: User):
    return await checked(service.promote(user["id"], model_id, force=req.force))


class DraftRubric(Body):
    count: int = Field(default=5, ge=1, le=12)
    guidance: str = Field(default="", max_length=2000)


@router.post("/{model_id}/draft/draft-rubric")
async def draft_rubric(model_id: UUID, req: DraftRubric, user: User):
    """Claude proposes a starting rubric; nothing is saved until the draft is edited."""
    return await checked(service.draft_rubric(user["id"], model_id, req.count, req.guidance))


@router.post("/{model_id}/draft/suggest-question")
async def suggest_question(model_id: UUID, user: User):
    return await checked(service.suggest_question(user["id"], model_id))


@router.get("/{model_id}/versions/{version_id}")
async def version(model_id: UUID, version_id: UUID, user: User):
    return await checked(service.version_detail(user["id"], model_id, version_id))


@router.post("/{model_id}/versions/{version_id}/restore")
async def restore(model_id: UUID, version_id: UUID, user: User):
    return await checked(service.rollback(user["id"], model_id, version_id))


@router.get("/{model_id}/examples")
async def examples(model_id: UUID, user: User):
    return await checked(service.list_examples(user["id"], model_id))


@router.get("/{model_id}/drop-folder")
async def get_drop_folder(model_id: UUID, user: User):
    """The eval's drop folder: files and pages added there become unlabeled examples."""
    await checked(service.get_detail(user["id"], model_id))
    return {"folder": await drop_folder.get(user["id"], model_id)}


@router.post("/{model_id}/drop-folder", status_code=201)
async def create_drop_folder(model_id: UUID, user: User):
    return {"folder": await checked(drop_folder.ensure(user["id"], model_id, user["id"]))}


@router.post("/{model_id}/drop-folder/sync")
async def sync_drop_folder(model_id: UUID, user: User):
    """Import what is new in the folder now instead of waiting for the next minute's sweep."""
    await checked(service.get_detail(user["id"], model_id))
    return await drop_folder.sync(model_id)


@router.post("/{model_id}/examples", status_code=201)
async def add_examples(model_id: UUID, req: AddExamples, user: User):
    return await checked(
        service.add_examples(
            user["id"], model_id, [e.model_dump() for e in req.examples], req.source
        )
    )


@router.post("/{model_id}/examples/generate", status_code=201)
async def generate(model_id: UUID, req: Generate, user: User):
    return await checked(
        service.generate_examples(user["id"], model_id, req.count, req.guidance, req.propose)
    )


@router.post("/{model_id}/examples/accept-suggestions")
async def accept_suggestions(model_id: UUID, user: User):
    return {"accepted": await checked(service.accept_suggestions(user["id"], model_id))}


@router.patch("/{model_id}/examples/{example_id}")
async def edit_example(model_id: UUID, example_id: UUID, req: EditExample, user: User):
    return await checked(
        service.update_example(user["id"], model_id, example_id, req.model_dump(exclude_unset=True))
    )


@router.delete("/{model_id}/examples/{example_id}", status_code=204)
async def delete_example(model_id: UUID, example_id: UUID, user: User):
    await checked(service.delete_example(user["id"], model_id, example_id))


@router.post("/{model_id}/predict")
async def predict(model_id: UUID, req: Predict, user: User):
    return await checked(
        service.predict(
            user["id"],
            model_id,
            req.item,
            which=req.version,
            version_id=req.version_id,
            caller=req.caller,
            ref=req.ref,
            metadata=req.metadata,
            run=req.run,
            step=req.step,
        )
    )


@router.post("/{model_id}/compare")
async def compare(model_id: UUID, req: Compare, user: User):
    return await checked(
        service.compare_items(
            user["id"],
            model_id,
            req.item_a,
            req.item_b,
            which=req.version,
            caller=req.caller,
            ref=req.ref,
            metadata=req.metadata,
            run=req.run,
            step=req.step,
        )
    )


@router.get("/{model_id}/predictions")
async def predictions(
    model_id: UUID,
    user: User,
    status: Literal["unreviewed", "escalated", "labeled", "dismissed", "all"] = "unreviewed",
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await checked(service.list_predictions(user["id"], model_id, status, limit, offset))


@router.post("/{model_id}/predictions/{prediction_id}/review")
async def review(model_id: UUID, prediction_id: UUID, req: Review, user: User):
    return await checked(
        service.review_prediction(
            user["id"],
            model_id,
            prediction_id,
            label=req.label,
            dismiss=req.dismiss,
            note=req.note,
            source=req.source,
        )
    )


@router.post("/{model_id}/feedback", status_code=201)
async def give_feedback(model_id: UUID, req: Feedback, user: User):
    """Attach a correction, outcome or downstream verdict to a served call, now or later."""
    return await checked(feedback.record(user["id"], model_id, **req.model_dump()))


@router.get("/{model_id}/monitoring")
async def monitor(model_id: UUID, user: User, days: int = Query(default=30, ge=1, le=365)):
    return await checked(monitoring.overview(user["id"], model_id, days))


@router.get("/{model_id}/label-queue")
async def label_queue(
    model_id: UUID, user: User, limit: int = Query(default=selection.QUEUE_SIZE, ge=1, le=100)
):
    """Unreviewed calls ranked by how much a label would teach the eval."""
    return await checked(selection.label_queue(user["id"], model_id, limit))


@router.post("/{model_id}/improve", status_code=202)
async def start_improve(model_id: UUID, user: User):
    """Search for better criteria in the background; the winner becomes the draft."""
    return await checked(improve.start(user["id"], model_id))


@router.get("/{model_id}/improve")
async def improve_status(model_id: UUID, user: User):
    return {"job": await checked(improve.latest(user["id"], model_id))}


class EvalAlert(Body):
    min_agreement: float = Field(default=0.8, gt=0, le=1)
    min_feedback: int = Field(default=5, ge=1, le=10_000)
    window_days: int = Field(default=7, ge=1, le=60)
    cooldown_hours: int = Field(default=24, ge=1, le=720)
    channels: list[Literal["slack", "email"]] = Field(default_factory=lambda: ["slack", "email"])


@router.put("/{model_id}/alert")
async def set_alert(model_id: UUID, user: User, req: EvalAlert | None = None):
    """Alert when production agreement drops below a floor; send null to turn it off."""
    from ..services.intuition import alerts as eval_alerts

    try:
        return {
            "alert": await eval_alerts.set_rule(
                user["id"], model_id, req.model_dump() if req else None
            )
        }
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


class MineProduction(Body):
    by: Literal["agent", "outcome", "satisfaction", "behavior", "tool_use", "task_type"] = (
        "satisfaction"
    )
    key: str = Field(default="frustrated", min_length=1, max_length=200)
    days: int = Field(default=30, ge=1, le=180)


@router.post("/{model_id}/mine-production")
async def mine_production(model_id: UUID, req: MineProduction, user: User):
    """Candidate criteria from users' corrections, repeats and pushback in a cohort's traces."""
    return await checked(mining.suggest(user["id"], model_id, req.by, req.key, req.days))


@router.post("/{model_id}/refine", status_code=202)
async def start_refine(model_id: UUID, user: User):
    """Refine the criteria pass by pass against mistakes, production feedback and
    environment checks; the result becomes the draft."""
    return await checked(rubric_builder.start(user["id"], model_id))


@router.get("/{model_id}/refine")
async def refine_status(model_id: UUID, user: User):
    return {"job": await checked(rubric_builder.latest(user["id"], model_id))}


@router.get("/{model_id}/credit")
async def outcome_credit(model_id: UUID, user: User):
    """How well this eval's decisions inside runs predict the runs' outcomes."""
    return await checked(runs.credit(user["id"], model_id))
