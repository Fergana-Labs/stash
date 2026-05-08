"""Stashes: create, upload artifacts, update summary, and serve."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, Form
from fastapi.responses import PlainTextResponse

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..models import (
    StashArtifactResponse,
    StashCreateRequest,
    StashCreateResponse,
    StashResponse,
    StashUpdateRequest,
)
from ..services import stash_service, storage_service, workspace_service

ws_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/stashes", tags=["stashes"],
)
public_router = APIRouter(prefix="/api/v1/stashes", tags=["stashes"])


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


@ws_router.post("", response_model=StashCreateResponse, status_code=201)
async def create_stash(
    workspace_id: UUID,
    req: StashCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    stash = await stash_service.create_stash(
        workspace_id=workspace_id,
        session_id=req.session_id,
        created_by=current_user["id"],
        agent_name=req.agent_name,
        cwd=req.cwd,
        files_touched=req.files_touched,
    )
    base = settings.PUBLIC_URL.rstrip("/")
    return StashCreateResponse(
        id=stash["id"], slug=stash["slug"], url=f"{base}/b/{stash['slug']}",
    )


@public_router.post("/{stash_id}/artifacts", status_code=201)
async def upload_artifact(
    stash_id: UUID,
    file: UploadFile,
    file_path: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    stash = await stash_service.get_stash_by_id(stash_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    if not await workspace_service.is_member(stash["workspace_id"], current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")

    content = await file.read()
    MAX_ARTIFACT_SIZE = 1 * 1024 * 1024  # 1MB per file
    if len(content) > MAX_ARTIFACT_SIZE:
        raise HTTPException(status_code=413, detail="Artifact too large (max 1 MB)")

    storage_key = await storage_service.upload_file(
        str(stash["workspace_id"]),
        file.filename or file_path.split("/")[-1],
        content,
        file.content_type or "application/octet-stream",
    )
    artifact = await stash_service.add_artifact(
        stash_id=stash_id,
        file_path=file_path,
        storage_key=storage_key,
        size_bytes=len(content),
    )
    return StashArtifactResponse(**artifact)


@public_router.post("/{stash_id}/transcript", status_code=201)
async def upload_stash_transcript(
    stash_id: UUID,
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    stash = await stash_service.get_stash_by_id(stash_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    if not await workspace_service.is_member(stash["workspace_id"], current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")

    content = await file.read()
    MAX_TRANSCRIPT_SIZE = 50 * 1024 * 1024
    if len(content) > MAX_TRANSCRIPT_SIZE:
        raise HTTPException(status_code=413, detail="Transcript too large (max 50 MB)")

    import gzip
    body = gzip.compress(content)
    name = file.filename or "transcript.jsonl"
    if not name.endswith(".gz"):
        name += ".gz"

    storage_key = await storage_service.upload_file(
        str(stash["workspace_id"]), name, body, "application/gzip",
    )
    await stash_service.set_transcript_key(stash_id, storage_key)
    return {"status": "ok"}


@public_router.patch("/{stash_id}", response_model=StashResponse)
async def update_stash(
    stash_id: UUID,
    req: StashUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    stash = await stash_service.get_stash_by_id(stash_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    if not await workspace_service.is_member(stash["workspace_id"], current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    updated = await stash_service.update_stash(
        stash_id, summary=req.summary, status=req.status,
    )
    return StashResponse(**updated)


# --- Public read endpoints (no auth required) ---


@public_router.get("/{slug}")
async def get_stash(
    slug: str,
    format: str | None = Query(None),
    current_user: dict | None = Depends(get_current_user_optional),
):
    stash = await stash_service.get_stash_by_slug(slug)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    artifacts = await stash_service.list_artifacts(stash["id"])

    if format == "text":
        return PlainTextResponse(
            _stash_to_text(stash, artifacts), media_type="text/markdown",
        )

    return {
        **StashResponse(**stash).model_dump(),
        "artifacts": [
            StashArtifactResponse(
                id=a["id"], file_path=a["file_path"],
                size_bytes=a["size_bytes"], created_at=a["created_at"],
            ).model_dump()
            for a in artifacts
        ],
    }


@public_router.get("/{slug}/files/{artifact_id}")
async def get_stash_artifact(slug: str, artifact_id: UUID):
    artifact = await stash_service.get_artifact(artifact_id)
    if not artifact or artifact["stash_slug"] != slug:
        raise HTTPException(status_code=404, detail="Artifact not found")

    content = await storage_service.download_file(artifact["storage_key"])
    return PlainTextResponse(
        content.decode("utf-8", errors="replace"), media_type="text/plain",
    )


@public_router.get("/{slug}/transcript")
async def get_stash_transcript(slug: str):
    stash = await stash_service.get_stash_by_slug(slug)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    transcript_key = await stash_service.get_transcript_key(stash["id"])
    if not transcript_key:
        raise HTTPException(status_code=404, detail="Transcript not available")

    import gzip
    raw = await storage_service.download_file(transcript_key)
    try:
        text = gzip.decompress(raw).decode("utf-8", errors="replace")
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    return PlainTextResponse(text, media_type="application/jsonl")


def _stash_to_text(stash: dict, artifacts: list[dict]) -> str:
    base = settings.PUBLIC_URL.rstrip("/")
    lines = [f"# Stash: {stash['slug']}", ""]

    if stash.get("agent_name"):
        lines.append(f"**Agent:** {stash['agent_name']}")
    if stash.get("cwd"):
        lines.append(f"**Directory:** {stash['cwd']}")
    lines.append(f"**Status:** {stash['status']}")
    lines.append(f"**Created:** {stash['created_at']}")
    lines.append("")

    if stash.get("summary"):
        lines.append("## Summary")
        lines.append("")
        lines.append(stash["summary"])
        lines.append("")
    elif stash["status"] in ("uploading", "summarizing"):
        lines.append("## Summary")
        lines.append("")
        lines.append("_Summary is being generated..._")
        lines.append("")

    if artifacts:
        lines.append("## Artifacts")
        lines.append("")
        for a in artifacts:
            url = f"{base}/api/v1/stashes/{stash['slug']}/files/{a['id']}"
            lines.append(f"- [{a['file_path']}]({url}) ({a['size_bytes']} bytes)")
        lines.append("")

    transcript_url = f"{base}/api/v1/stashes/{stash['slug']}/transcript"
    lines.append("## Transcript")
    lines.append("")
    if stash.get("has_transcript"):
        lines.append(f"Full session transcript: [download]({transcript_url})")
    else:
        lines.append("_Transcript not yet available._")
    lines.append("")

    return "\n".join(lines)
