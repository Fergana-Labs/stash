"""Session bundles: create, upload artifacts, update summary, and serve."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, Form
from fastapi.responses import PlainTextResponse

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..models import (
    BundleArtifactResponse,
    BundleCreateRequest,
    BundleCreateResponse,
    BundleResponse,
    BundleUpdateRequest,
)
from ..services import bundle_service, storage_service, workspace_service

ws_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/bundles", tags=["bundles"],
)
public_router = APIRouter(prefix="/api/v1/bundles", tags=["bundles"])


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


@ws_router.post("", response_model=BundleCreateResponse, status_code=201)
async def create_bundle(
    workspace_id: UUID,
    req: BundleCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    bundle = await bundle_service.create_bundle(
        workspace_id=workspace_id,
        session_id=req.session_id,
        created_by=current_user["id"],
        agent_name=req.agent_name,
        cwd=req.cwd,
        files_touched=req.files_touched,
    )
    base = settings.PUBLIC_URL.rstrip("/")
    return BundleCreateResponse(
        id=bundle["id"], slug=bundle["slug"], url=f"{base}/b/{bundle['slug']}",
    )


@public_router.post("/{bundle_id}/artifacts", status_code=201)
async def upload_artifact(
    bundle_id: UUID,
    file: UploadFile,
    file_path: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    bundle = await bundle_service.get_bundle_by_id(bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if not await workspace_service.is_member(bundle["workspace_id"], current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")

    content = await file.read()
    MAX_ARTIFACT_SIZE = 1 * 1024 * 1024  # 1MB per file
    if len(content) > MAX_ARTIFACT_SIZE:
        raise HTTPException(status_code=413, detail="Artifact too large (max 1 MB)")

    storage_key = await storage_service.upload_file(
        str(bundle["workspace_id"]),
        file.filename or file_path.split("/")[-1],
        content,
        file.content_type or "application/octet-stream",
    )
    artifact = await bundle_service.add_artifact(
        bundle_id=bundle_id,
        file_path=file_path,
        storage_key=storage_key,
        size_bytes=len(content),
    )
    return BundleArtifactResponse(**artifact)


@public_router.post("/{bundle_id}/transcript", status_code=201)
async def upload_bundle_transcript(
    bundle_id: UUID,
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    bundle = await bundle_service.get_bundle_by_id(bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if not await workspace_service.is_member(bundle["workspace_id"], current_user["id"]):
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
        str(bundle["workspace_id"]), name, body, "application/gzip",
    )
    await bundle_service.set_transcript_key(bundle_id, storage_key)
    return {"status": "ok"}


@public_router.patch("/{bundle_id}", response_model=BundleResponse)
async def update_bundle(
    bundle_id: UUID,
    req: BundleUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    bundle = await bundle_service.get_bundle_by_id(bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if not await workspace_service.is_member(bundle["workspace_id"], current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    updated = await bundle_service.update_bundle(
        bundle_id, summary=req.summary, status=req.status,
    )
    return BundleResponse(**updated)


# --- Public read endpoints (no auth required) ---


@public_router.get("/{slug}")
async def get_bundle(
    slug: str,
    format: str | None = Query(None),
    current_user: dict | None = Depends(get_current_user_optional),
):
    bundle = await bundle_service.get_bundle_by_slug(slug)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    artifacts = await bundle_service.list_artifacts(bundle["id"])

    if format == "text":
        return PlainTextResponse(
            _bundle_to_text(bundle, artifacts), media_type="text/markdown",
        )

    return {
        **BundleResponse(**bundle).model_dump(),
        "artifacts": [
            BundleArtifactResponse(
                id=a["id"], file_path=a["file_path"],
                size_bytes=a["size_bytes"], created_at=a["created_at"],
            ).model_dump()
            for a in artifacts
        ],
    }


@public_router.get("/{slug}/files/{artifact_id}")
async def get_bundle_artifact(slug: str, artifact_id: UUID):
    artifact = await bundle_service.get_artifact(artifact_id)
    if not artifact or artifact["bundle_slug"] != slug:
        raise HTTPException(status_code=404, detail="Artifact not found")

    content = await storage_service.download_file(artifact["storage_key"])
    return PlainTextResponse(
        content.decode("utf-8", errors="replace"), media_type="text/plain",
    )


@public_router.get("/{slug}/transcript")
async def get_bundle_transcript(slug: str):
    bundle = await bundle_service.get_bundle_by_slug(slug)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    transcript_key = await bundle_service.get_transcript_key(bundle["id"])
    if not transcript_key:
        raise HTTPException(status_code=404, detail="Transcript not available")

    import gzip
    raw = await storage_service.download_file(transcript_key)
    try:
        text = gzip.decompress(raw).decode("utf-8", errors="replace")
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    return PlainTextResponse(text, media_type="application/jsonl")


def _bundle_to_text(bundle: dict, artifacts: list[dict]) -> str:
    base = settings.PUBLIC_URL.rstrip("/")
    lines = [f"# Session Bundle: {bundle['slug']}", ""]

    if bundle.get("agent_name"):
        lines.append(f"**Agent:** {bundle['agent_name']}")
    if bundle.get("cwd"):
        lines.append(f"**Directory:** {bundle['cwd']}")
    lines.append(f"**Status:** {bundle['status']}")
    lines.append(f"**Created:** {bundle['created_at']}")
    lines.append("")

    if bundle.get("summary"):
        lines.append("## Summary")
        lines.append("")
        lines.append(bundle["summary"])
        lines.append("")
    elif bundle["status"] in ("uploading", "summarizing"):
        lines.append("## Summary")
        lines.append("")
        lines.append("_Summary is being generated..._")
        lines.append("")

    if artifacts:
        lines.append("## Artifacts")
        lines.append("")
        for a in artifacts:
            url = f"{base}/api/v1/bundles/{bundle['slug']}/files/{a['id']}"
            lines.append(f"- [{a['file_path']}]({url}) ({a['size_bytes']} bytes)")
        lines.append("")

    transcript_url = f"{base}/api/v1/bundles/{bundle['slug']}/transcript"
    lines.append("## Transcript")
    lines.append("")
    if bundle.get("has_transcript"):
        lines.append(f"Full session transcript: [download]({transcript_url})")
    else:
        lines.append("_Transcript not yet available._")
    lines.append("")

    return "\n".join(lines)
