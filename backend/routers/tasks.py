"""Polling endpoint for Celery task status.

The import and export endpoints return a `task_id`. The frontend polls
this route to know when the task finishes and to receive its result
(storage_key, page_id, drive_file_id, etc.) or failure reason.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..celery_app import celery
from ..services import task_service

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskStatus(BaseModel):
    task_id: str
    state: str  # PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED
    result: dict | list | str | int | float | bool | None = None
    error: str | None = None


@router.get("/{task_id}", response_model=TaskStatus)
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")
    if not await task_service.user_can_read_task(task_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Task not found")
    async_result = celery.AsyncResult(task_id)
    state = async_result.state
    if state == "SUCCESS":
        return TaskStatus(task_id=task_id, state=state, result=async_result.result)
    if state == "FAILURE":
        return TaskStatus(task_id=task_id, state=state, error="Task failed")
    return TaskStatus(task_id=task_id, state=state)
