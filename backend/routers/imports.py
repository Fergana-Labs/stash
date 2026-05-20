"""Import endpoints (Google Drive, Git).

Each endpoint resolves the right Celery task via the integration
registry, dispatches it, and returns a task_id the client can poll at
GET /api/v1/tasks/{task_id}.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..celery_app import celery
from ..integrations.registry import resolve_importer
from ..services import permission_service

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/imports", tags=["imports"])


async def _check_workspace_access(workspace_id: UUID, user_id: UUID) -> None:
    role = await permission_service.get_workspace_role(workspace_id, user_id)
    if role not in ("owner", "admin", "editor"):
        raise HTTPException(status_code=404, detail="Workspace not found")


class GitImportRequest(BaseModel):
    url: str
    ref: str | None = None
    subpath: str | None = None
    pat: str | None = None
    folder_id: UUID | None = None


class GitImportResponse(BaseModel):
    task_id: str


@router.post("/git", response_model=GitImportResponse)
async def import_git(
    workspace_id: UUID,
    body: GitImportRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_workspace_access(workspace_id, current_user["id"])
    task_name = resolve_importer("github", "repo")
    async_result = celery.send_task(
        task_name,
        kwargs={
            "user_id": str(current_user["id"]),
            "workspace_id": str(workspace_id),
            "url": body.url,
            "ref": body.ref,
            "subpath": body.subpath,
            "pat": body.pat,
            "folder_id": str(body.folder_id) if body.folder_id else None,
        },
    )
    return GitImportResponse(task_id=async_result.id)


class GoogleDriveImportRequest(BaseModel):
    file_ids: list[str]
    folder_id: UUID | None = None


class GoogleDriveImportResponse(BaseModel):
    task_ids: list[str]


@router.post("/google-drive", response_model=GoogleDriveImportResponse)
async def import_google_drive(
    workspace_id: UUID,
    body: GoogleDriveImportRequest,
    current_user: dict = Depends(get_current_user),
):
    """Dispatch one task per selected Drive file.

    The Celery task fetches each file's MIME type itself and routes
    internally — the API layer doesn't need to resolve per-MIME importers.
    """
    await _check_workspace_access(workspace_id, current_user["id"])
    task_name = resolve_importer("google", "drive_file")
    task_ids: list[str] = []
    for fid in body.file_ids:
        async_result = celery.send_task(
            task_name,
            kwargs={
                "user_id": str(current_user["id"]),
                "workspace_id": str(workspace_id),
                "file_id": fid,
                "folder_id": str(body.folder_id) if body.folder_id else None,
            },
        )
        task_ids.append(async_result.id)
    return GoogleDriveImportResponse(task_ids=task_ids)


class NotionImportRequest(BaseModel):
    # Accepts either page URLs or database URLs (or bare 32-hex / dashed
    # UUIDs of either). The task probes pages first, falls back to
    # databases on 404 — single endpoint, single dialog.
    urls: list[str]
    folder_id: UUID | None = None


class NotionImportResponse(BaseModel):
    task_ids: list[str]


@router.post("/notion", response_model=NotionImportResponse)
async def import_notion(
    workspace_id: UUID,
    body: NotionImportRequest,
    current_user: dict = Depends(get_current_user),
):
    """One task per selected Notion resource (page or database).

    Pages with subpages are imported recursively into a folder named
    after the parent. Databases become tables. Each task auto-detects
    which is which by probing the Notion API."""
    await _check_workspace_access(workspace_id, current_user["id"])
    task_name = resolve_importer("notion", "resource")
    task_ids: list[str] = []
    for url in body.urls:
        async_result = celery.send_task(
            task_name,
            kwargs={
                "user_id": str(current_user["id"]),
                "workspace_id": str(workspace_id),
                "resource_id": url,
                "folder_id": str(body.folder_id) if body.folder_id else None,
            },
        )
        task_ids.append(async_result.id)
    return NotionImportResponse(task_ids=task_ids)
