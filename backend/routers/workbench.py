"""User-facing agent workbench; all mutations are authenticated and owner-scoped."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user
from ..config import settings
from ..database import get_pool
from ..services.rm import workbench as service
from ..services.rm import workbench_auto as automatic
from ..services.rm import workbench_grader as engine
from ..services.rm import workbench_instructions as instructions
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/rm/workbench", tags=["workbench"], dependencies=[Depends(require_reward_models)]
)
Verdict = Literal["meets", "violates", "insufficient_evidence", "not_applicable"]
Kind = Literal["judge_error", "agent_error", "both", "requirement_change", "unclear", "label_only"]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateGrader(Body):
    name: str = Field(min_length=1, max_length=160)
    scope: dict = Field(default_factory=dict)
    config: dict


class UpdateGrader(Body):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    enabled: bool | None = None
    scope: dict | None = None


class CreateVersion(Body):
    config: dict


class CreateFeedback(Body):
    trace_id: UUID
    assessment_id: UUID | None = None
    evaluation_id: UUID | None = None
    target_step_id: UUID | None = None
    comment: str = Field(min_length=1, max_length=6000)
    proposed_verdict: Verdict | None = None
    change_kind: Kind = "unclear"


class ReviewFeedback(Body):
    decision: Literal["accept", "reject"]
    proposed_verdict: Verdict | None = None
    change_kind: Kind | None = None


class AuditLabel(Body):
    verdict: Verdict
    comment: str | None = Field(default=None, max_length=6000)


class EditChange(Body):
    content: dict | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)


class Reviewer(Body):
    email: str = Field(min_length=3, max_length=320)


class Delivery(Body):
    session_id: str = Field(min_length=1, max_length=300)
    source_format: Literal["codex", "claude_code"]
    repository: str = Field(min_length=1, max_length=2000)


class Rollback(Body):
    version_id: UUID


class Release(Body):
    accept_unmeasured: bool = False


class InstructionRollback(Body):
    change_id: UUID | None = None


async def checked(coro):
    try:
        return await coro
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/status")
async def status(user=Depends(get_current_user)):
    return {
        "provider": "jev",
        "configured": bool(settings.TYPESAFE_API_KEY),
        "model": settings.JEV_MODEL,
        "default_prompt": engine.DEFAULT_PROMPT,
        "default_criteria": engine.DEFAULT_CRITERIA,
    }


@router.get("/graders")
async def graders(user=Depends(get_current_user)):
    return await service.list_graders(user["id"])


@router.post("/graders", status_code=201)
async def create_grader(req: CreateGrader, user=Depends(get_current_user)):
    return await checked(service.create_grader(user["id"], req.name, req.scope, req.config))


@router.get("/graders/{grader_id}")
async def grader(grader_id: UUID, user=Depends(get_current_user)):
    return await checked(service.grader_detail(user["id"], grader_id))


@router.patch("/graders/{grader_id}")
async def update_grader(grader_id: UUID, req: UpdateGrader, user=Depends(get_current_user)):
    return await checked(
        service.update_grader(user["id"], grader_id, req.model_dump(exclude_none=True))
    )


@router.post("/graders/{grader_id}/versions", status_code=201)
async def version(grader_id: UUID, req: CreateVersion, user=Depends(get_current_user)):
    return await checked(service.draft_version(user["id"], grader_id, req.config))


@router.post("/graders/{grader_id}/rollback")
async def rollback(grader_id: UUID, req: Rollback, user=Depends(get_current_user)):
    return await checked(service.rollback_grader(user["id"], grader_id, req.version_id))


@router.get("/traces/{trace_id}/evaluation")
async def evaluation(trace_id: UUID, user=Depends(get_current_user)):
    return await checked(automatic.detail(user["id"], trace_id))


@router.get("/traces/{trace_id}/evaluation/{evaluation_id}")
async def evaluation_history(trace_id: UUID, evaluation_id: UUID, user=Depends(get_current_user)):
    return await checked(automatic.historical(user["id"], trace_id, evaluation_id))


@router.get("/traces/{trace_id}/assessments")
async def assessments(trace_id: UUID, user=Depends(get_current_user)):
    return await checked(service.trace_assessments(user["id"], trace_id))


@router.post("/traces/{trace_id}/assess", status_code=202)
async def assess(trace_id: UUID, user=Depends(get_current_user)):
    return await checked(service.queue_trace(user["id"], trace_id))


@router.get("/review-samples")
async def review_samples(user=Depends(get_current_user)):
    return await service.review_samples(user["id"])


@router.post("/assessments/{assessment_id}/label", status_code=201)
async def label(assessment_id: UUID, req: AuditLabel, user=Depends(get_current_user)):
    return await checked(
        service.label_assessment(user["id"], assessment_id, req.verdict, req.comment)
    )


@router.get("/feedback")
async def feedback(user=Depends(get_current_user)):
    return await service.list_feedback(user["id"])


@router.get("/feedback/{feedback_id}")
async def feedback_detail(feedback_id: UUID, user=Depends(get_current_user)):
    return await checked(service.feedback_detail(user["id"], feedback_id))


@router.post("/feedback", status_code=201)
async def new_feedback(req: CreateFeedback, user=Depends(get_current_user)):
    if not req.comment.strip():
        raise HTTPException(422, "Comment must not be blank")
    return await checked(service.create_feedback(user["id"], req.model_dump()))


@router.post("/feedback/{feedback_id}/review")
async def review(feedback_id: UUID, req: ReviewFeedback, user=Depends(get_current_user)):
    return await checked(
        service.review_feedback(
            user["id"], feedback_id, req.decision, req.proposed_verdict, req.change_kind
        )
    )


@router.post("/feedback/{feedback_id}/retry", status_code=202)
async def retry_feedback(feedback_id: UUID, user=Depends(get_current_user)):
    return await checked(service.retry_feedback(user["id"], feedback_id))


@router.get("/changes")
async def changes(user=Depends(get_current_user)):
    return await service.list_changes(user["id"])


@router.get("/changes/{change_id}")
async def change(change_id: UUID, user=Depends(get_current_user)):
    return await checked(service.change_detail(user["id"], change_id))


@router.patch("/changes/{change_id}")
async def edit_change(change_id: UUID, req: EditChange, user=Depends(get_current_user)):
    return await checked(
        service.edit_change(user["id"], change_id, req.model_dump(exclude_none=True))
    )


@router.post("/changes/{change_id}/check", status_code=202)
async def check_change(change_id: UUID, user=Depends(get_current_user)):
    return await checked(service.request_check(user["id"], change_id))


@router.post("/changes/{change_id}/release")
async def release(change_id: UUID, req: Release | None = None, user=Depends(get_current_user)):
    return await checked(
        service.release_change(
            user["id"], change_id, accept_unmeasured=bool(req and req.accept_unmeasured)
        )
    )


@router.post("/changes/{change_id}/reject")
async def reject(change_id: UUID, user=Depends(get_current_user)):
    return await checked(service.reject_change(user["id"], change_id))


@router.get("/traces/{trace_id}/reviewers")
async def reviewers(trace_id: UUID, user=Depends(get_current_user)):
    trace = await checked(service.trace_access(user["id"], trace_id))
    rows = await get_pool().fetch(
        """SELECT r.user_id,u.display_name,u.email FROM rm_wb_trace_reviewers r
        JOIN users u ON u.id=r.user_id WHERE r.trace_id=$1""",
        trace_id,
    )
    return {"owner_user_id": trace["owner_user_id"], "reviewers": [dict(r) for r in rows]}


@router.post("/traces/{trace_id}/reviewers")
async def add_reviewer(trace_id: UUID, req: Reviewer, user=Depends(get_current_user)):
    await checked(service.trace_access(user["id"], trace_id, write=True))
    target = await get_pool().fetchval(
        "SELECT id FROM users WHERE lower(email)=lower($1)", req.email.strip()
    )
    if target is None:
        raise HTTPException(404, "No Stash account found for that email")
    await get_pool().execute(
        "INSERT INTO rm_wb_trace_reviewers(trace_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
        trace_id,
        target,
    )
    return await reviewers(trace_id, user)


@router.delete("/traces/{trace_id}/reviewers/{user_id}")
async def remove_reviewer(trace_id: UUID, user_id: UUID, user=Depends(get_current_user)):
    await checked(service.trace_access(user["id"], trace_id, write=True))
    await get_pool().execute(
        "DELETE FROM rm_wb_trace_reviewers WHERE trace_id=$1 AND user_id=$2", trace_id, user_id
    )
    return await reviewers(trace_id, user)


@router.post("/instruction-deliveries")
async def deliver(req: Delivery, user=Depends(get_current_user)):
    return await checked(
        instructions.deliver(user["id"], req.session_id, req.source_format, req.repository)
    )


@router.get("/instruction-deliveries")
async def deliveries(trace_id: UUID | None = None, user=Depends(get_current_user)):
    return await instructions.list_deliveries(user["id"], trace_id)


@router.get("/graders/{grader_id}/instruction-releases")
async def instruction_releases(grader_id: UUID, user=Depends(get_current_user)):
    await checked(service.owned_grader(user["id"], grader_id))
    return await instructions.list_releases(user["id"], grader_id)


@router.post("/graders/{grader_id}/instruction-rollback")
async def instruction_rollback(
    grader_id: UUID, req: InstructionRollback, user=Depends(get_current_user)
):
    return await checked(instructions.rollback(user["id"], grader_id, req.change_id))
