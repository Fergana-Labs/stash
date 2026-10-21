"""Compute owned comparison features through the trusted cloud worker."""

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user
from ..services.rm import feature_jobs
from ..services.rm.adapters import CanonicalStep
from .customer_heads import checked
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/rm/customer-feature-jobs",
    tags=["reward-models"],
    dependencies=[Depends(require_reward_models)],
)


class FeatureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shared_model_id: UUID
    context: list[CanonicalStep] = Field(min_length=1, max_length=100)
    task_context: dict = Field(default_factory=dict)
    a: CanonicalStep
    b: CanonicalStep
    trace_id: UUID | None = None


@router.post("", status_code=202)
async def create(req: FeatureRequest, user: dict = Depends(get_current_user)):
    from ..tasks.reward_models import compute_customer_features

    result = await checked(
        feature_jobs.create(
            user["id"],
            req.shared_model_id,
            [asdict(s) for s in req.context],
            req.task_context,
            asdict(req.a),
            asdict(req.b),
            req.trace_id,
        )
    )
    try:
        compute_customer_features.delay(str(result["id"]))
    except Exception:
        pass  # The periodic reconciler dispatches the durable queued job.
    return result


@router.get("/{job_id}")
async def detail(job_id: UUID, user: dict = Depends(get_current_user)):
    return await checked(feature_jobs.detail(user["id"], job_id))


@router.post("/{job_id}/retry", status_code=202)
async def retry(job_id: UUID, user: dict = Depends(get_current_user)):
    from ..tasks.reward_models import compute_customer_features

    result = await checked(feature_jobs.retry(user["id"], job_id))
    try:
        compute_customer_features.delay(str(result["id"]))
    except Exception:
        pass  # The queued job is durable; reconciliation dispatches it.
    return result
