"""Admin router: cross-user analytics. Gated by a shared X-Admin-Token header."""

import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel

from ..config import settings
from ..services import (
    admin_analytics_service,
    cohort_service,
    github_skill_import,
    security_audit_service,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def _record_admin_access(
    request: Request,
    *,
    action: str,
    token_present: bool,
    status_code: int | None = None,
) -> None:
    client_host = request.client.host if request.client else None
    query_string = request.url.query or None
    metadata = {
        "client_host_hash": security_audit_service.hash_value(client_host),
        "query_hash": security_audit_service.hash_value(query_string),
        "token_present": token_present,
    }
    # Granted events omit status_code: the token check passes before the
    # handler runs, so the final response status is unknown here.
    if status_code is not None:
        metadata["status_code"] = status_code
    await security_audit_service.record_event(
        action=action,
        actor_user_id=None,
        owner_user_id=None,
        target_type="admin_endpoint",
        target_id=request.scope["route"].path,
        metadata=metadata,
    )


async def require_admin_token(
    request: Request, x_admin_token: str | None = Header(default=None)
) -> None:
    expected = settings.ADMIN_PASSWORD
    if not expected:
        await _record_admin_access(
            request,
            action="admin.access_disabled",
            status_code=503,
            token_present=bool(x_admin_token),
        )
        raise HTTPException(
            status_code=503, detail="Admin endpoints disabled (ADMIN_PASSWORD unset)"
        )
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        await _record_admin_access(
            request,
            action="admin.access_denied",
            status_code=401,
            token_present=bool(x_admin_token),
        )
        raise HTTPException(status_code=401, detail="Invalid admin token")
    await _record_admin_access(
        request,
        action="admin.access_granted",
        token_present=True,
    )


@router.get("/cohorts/engagement", dependencies=[Depends(require_admin_token)])
async def engagement_cohorts(
    bucket: str = Query("month", pattern="^(month|week|rolling_7d)$"),
    mode: str = Query("standard", pattern="^(standard|future)$"),
    max_period: int | None = Query(None, ge=1, le=104),
    events_filter: str = Query("all", pattern="^(all|active)$"),
):
    return await cohort_service.get_engagement_cohorts(
        bucket=bucket,
        mode=mode,
        max_period=max_period,
        events_filter=events_filter,
    )


@router.get("/analytics/summary", dependencies=[Depends(require_admin_token)])
async def analytics_summary(days: int = Query(7, ge=1, le=90)):
    return await admin_analytics_service.get_summary(days=days)


@router.get("/analytics/onboarding-funnel", dependencies=[Depends(require_admin_token)])
async def analytics_onboarding_funnel(
    days: int = Query(30, ge=1, le=180),
    path: str | None = Query(None, pattern="^(migrant|memory|sharing)$"),
):
    return await admin_analytics_service.get_onboarding_funnel(days=days, path=path)


@router.get("/analytics/path-mix", dependencies=[Depends(require_admin_token)])
async def analytics_path_mix(
    days: int = Query(30, ge=1, le=180),
    bucket: str = Query("day", pattern="^(day|week)$"),
):
    return await admin_analytics_service.get_path_mix(days=days, bucket=bucket)


@router.get("/analytics/surface-mix", dependencies=[Depends(require_admin_token)])
async def analytics_surface_mix(
    days: int = Query(30, ge=1, le=180),
    bucket: str = Query("day", pattern="^(day|week)$"),
):
    return await admin_analytics_service.get_surface_mix(days=days, bucket=bucket)


@router.get("/analytics/top-events", dependencies=[Depends(require_admin_token)])
async def analytics_top_events(
    days: int = Query(30, ge=1, le=180),
    limit: int = Query(20, ge=1, le=100),
):
    return await admin_analytics_service.get_top_events(days=days, limit=limit)


# --- Discover catalog: import / remove GitHub skill repos ---


class RepoRequest(BaseModel):
    repo_url: str


@router.get("/discover-skills", dependencies=[Depends(require_admin_token)])
async def list_discover_skills():
    """Imported GitHub skills, grouped by source repo."""
    return {"repos": await github_skill_import.list_imported_repos()}


@router.post("/discover-skills/import", dependencies=[Depends(require_admin_token)])
async def import_discover_skill(req: RepoRequest):
    """Import (or re-import) every SKILL.md folder in a public GitHub repo."""
    try:
        summary = await github_skill_import.import_repo(req.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if summary["skills_found"] == 0:
        raise HTTPException(status_code=404, detail="No SKILL.md folders found in that repo")
    return summary


@router.post("/discover-skills/remove", dependencies=[Depends(require_admin_token)])
async def remove_discover_skill(req: RepoRequest):
    """Remove every imported skill from a repo."""
    try:
        removed = await github_skill_import.remove_repo_skills(req.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"repo_url": req.repo_url, "removed": removed}


# --- Workspaces: org-owned scopes, managed by ops (like plans) ---


class WorkspaceRequest(BaseModel):
    name: str
    domain: str


class MemberRequest(BaseModel):
    email: str


class WorkspaceKeyRequest(BaseModel):
    name: str
    access: str


@router.post("/workspaces", dependencies=[Depends(require_admin_token)])
async def create_workspace(req: WorkspaceRequest):
    """Create a workspace and its login-less scope user; backfill-enroll
    existing verified users on the domain. Returns a bootstrap full-access
    key for ops to connect agent credentials and sources as the workspace."""
    from ..auth import create_api_key
    from ..services import workspace_service

    domain = req.domain.strip()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not domain or domain != domain.lower() or "@" in domain or "." not in domain:
        raise HTTPException(
            status_code=400, detail="domain must be a bare lowercase domain like 'example.com'"
        )
    try:
        workspace = await workspace_service.create_workspace(req.name.strip(), domain)
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"workspace for {domain} already exists")
        raise
    bootstrap_key = await create_api_key(
        workspace["scope_user_id"], name="workspace bootstrap", key_type="machine", access="full"
    )
    return {
        "workspace_id": str(workspace["id"]),
        "scope_user_id": str(workspace["scope_user_id"]),
        "bootstrap_api_key": bootstrap_key,
    }


@router.get("/workspaces", dependencies=[Depends(require_admin_token)])
async def list_workspaces():
    from ..services import workspace_service

    return {"workspaces": await workspace_service.list_workspaces()}


@router.post("/workspaces/{workspace_id}/members", dependencies=[Depends(require_admin_token)])
async def add_workspace_member(workspace_id: UUID, req: MemberRequest):
    """Explicitly add a member by email — the path for people outside the
    workspace's domain (contractors etc.)."""
    from ..services import user_service, workspace_service

    if not await workspace_service.get_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    user = await user_service.get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=404, detail=f"No user with email {req.email}")
    await workspace_service.add_member(workspace_id, user["id"])
    return {"workspace_id": str(workspace_id), "user_id": str(user["id"])}


@router.delete(
    "/workspaces/{workspace_id}/members/{user_id}",
    dependencies=[Depends(require_admin_token)],
)
async def remove_workspace_member(workspace_id: UUID, user_id: UUID):
    from ..services import workspace_service

    if not await workspace_service.remove_member(workspace_id, user_id):
        raise HTTPException(status_code=404, detail="Membership not found")
    return {"workspace_id": str(workspace_id), "user_id": str(user_id)}


@router.post("/workspaces/{workspace_id}/keys", dependencies=[Depends(require_admin_token)])
async def mint_workspace_key(workspace_id: UUID, req: WorkspaceKeyRequest):
    """Mint an API key on the workspace's scope user. Production agents get
    access='read': full read + transcript upload, no destructive power."""
    from ..auth import API_KEY_ACCESS_LEVELS, create_api_key
    from ..services import workspace_service

    if req.access not in API_KEY_ACCESS_LEVELS:
        raise HTTPException(status_code=400, detail=f"unknown access level: {req.access}")
    workspace = await workspace_service.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    key = await create_api_key(
        workspace["scope_user_id"], name=req.name, key_type="machine", access=req.access
    )
    return {"workspace_id": str(workspace_id), "api_key": key, "access": req.access}


class PlanRequest(BaseModel):
    plan: str


@router.post("/users/{user_id}/plan", dependencies=[Depends(require_admin_token)])
async def set_user_plan(user_id: UUID, req: PlanRequest):
    """Set a user's billing entitlement. 'enterprise' unlocks unlimited
    sleep-time curator runs; granted manually after the sales conversation."""
    if req.plan not in ("free", "enterprise"):
        raise HTTPException(status_code=400, detail=f"unknown plan: {req.plan}")
    from ..database import get_pool

    result = await get_pool().execute("UPDATE users SET plan = $2 WHERE id = $1", user_id, req.plan)
    if not result.endswith(" 1"):
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": str(user_id), "plan": req.plan}
