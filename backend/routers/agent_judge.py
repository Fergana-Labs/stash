"""Agent Judge API: investigate a trace for unsupported claims, and read past investigations.

Investigations made while grading an eval with the agent judge are listed here
too, so every verdict on a trace can be inspected: the claims ledger, the
findings with step citations, and what it cost.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from ..auth import get_current_user
from ..services.agent_judge import grading
from .reward_models import require_reward_models

router = APIRouter(
    prefix="/api/v1/agent-judge",
    tags=["agent-judge"],
    dependencies=[Depends(require_reward_models)],
)


class Investigate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: UUID


@router.post("/investigations", status_code=202)
async def investigate(body: Investigate, user: dict = Depends(get_current_user)):
    if not grading.configured():
        raise HTTPException(
            status_code=503, detail="The agent judge needs ANTHROPIC_API_KEY on the backend"
        )
    try:
        report_id = await grading.start(user["id"], body.trace_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from ..tasks.agent_judge import investigate as task

    task.delay(str(report_id))
    return {"id": report_id, "status": "running"}


@router.get("/traces/{trace_id}/reports")
async def trace_reports(trace_id: UUID, user: dict = Depends(get_current_user)):
    return {"reports": await grading.reports(user["id"], trace_id)}


@router.get("/reports/{report_id}")
async def get_report(report_id: UUID, user: dict = Depends(get_current_user)):
    found = await grading.report(user["id"], report_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return found
