"""Export endpoints (slide pages → PDF / PPTX / Google Slides).

Resolves the format-specific task via the exporter registry and
dispatches it. Returns a task_id the client polls.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..celery_app import celery
from ..database import get_pool
from ..integrations.registry import resolve_exporter
from ..services import permission_service, task_service

router = APIRouter(prefix="/api/v1/pages", tags=["exports"])


class ExportRequest(BaseModel):
    format: str = Field(..., pattern=r"^(pdf|pptx|gslides)$")


class ExportResponse(BaseModel):
    task_id: str


@router.post("/{page_id}/export", response_model=ExportResponse)
async def export_page(
    page_id: UUID,
    body: ExportRequest,
    current_user: dict = Depends(get_current_user),
):
    pool = get_pool()
    page = await pool.fetchrow(
        "SELECT id, workspace_id, content_type, html_layout FROM pages WHERE id = $1",
        page_id,
    )
    if not page:
        raise HTTPException(status_code=404, detail="page not found")
    if page["content_type"] != "html" or page["html_layout"] != "fixed-aspect":
        raise HTTPException(
            status_code=400,
            detail="export only supported for fixed-aspect HTML slide pages",
        )
    can_read = await permission_service.check_access(
        "page",
        page_id,
        current_user["id"],
        workspace_id=page["workspace_id"],
    )
    if not can_read:
        raise HTTPException(status_code=404, detail="page not found")

    task_name = resolve_exporter(body.format)
    task_id = str(uuid4())
    await task_service.register_task(
        task_id=task_id,
        user_id=current_user["id"],
        workspace_id=page["workspace_id"],
        task_type=f"export:{body.format}",
        object_type="page",
        object_id=page_id,
    )
    celery.send_task(
        task_name,
        kwargs={
            "user_id": str(current_user["id"]),
            "page_id": str(page_id),
        },
        task_id=task_id,
    )
    return ExportResponse(task_id=task_id)
