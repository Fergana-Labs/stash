"""Developer platform: the console API for External Multiplayer.

Self-serve counterpart to the admin workspace endpoints. A user activates the
platform (creating a one-man, invite-only workspace when they have none),
mints machine keys on the workspace's scope user, and manages the orgs their
product's sessions create. Org listing and editing are scope-based like every
other surface: the console sends X-Stash-Scope with the workspace's scope
user id.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import API_KEY_ACCESS_LEVELS, create_api_key, get_current_user, get_scope
from ..services import agent_service, org_service, permission_service, prompts, workspace_service
from .curator_log import curator_runs

router = APIRouter(prefix="/api/v1/me/developer", tags=["developer"])
orgs_router = APIRouter(prefix="/api/v1/me/orgs", tags=["developer"])


class ActivateRequest(BaseModel):
    workspace_id: UUID | None = Field(
        None,
        description="Activate on this workspace (must be a member); omit to "
        "create a one-man developer workspace",
    )
    name: str | None = Field(None, max_length=255)


class DeveloperKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    access: str = "read"


class OrgUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    share_wiki: bool | None = None


async def _require_member_workspace(workspace_id: UUID, user_id: UUID) -> dict:
    workspace = await workspace_service.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not await permission_service.is_workspace_member(workspace["scope_user_id"], user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    return workspace


async def _require_active_workspace(scope_user_id: UUID) -> dict:
    workspace = await org_service.workspace_for_scope(scope_user_id)
    if workspace is None or workspace["external_wiki_folder_id"] is None:
        raise HTTPException(
            status_code=400,
            detail="scope is not an active developer workspace — activate first",
        )
    return workspace


@router.post("/activate")
async def activate_developer_platform(
    req: ActivateRequest, current_user: dict = Depends(get_current_user)
):
    """Turn on the developer platform. With a workspace_id, activates it for
    that workspace; without one, creates a fresh one-man invite-only
    workspace — the solo-developer path."""
    if req.workspace_id is not None:
        workspace = await _require_member_workspace(req.workspace_id, current_user["id"])
    else:
        name = req.name or f"{current_user['display_name'] or current_user['name']} (Developer)"
        workspace = await workspace_service.create_workspace(
            name, domain=None, created_by=current_user["id"]
        )
    return await org_service.activate(workspace["id"], current_user["id"])


@router.post("/keys")
async def mint_developer_key(
    req: DeveloperKeyRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Mint a machine key on the developer workspace's scope user — the key a
    product backend (e.g. Heavi) uses for every Stash call. Console sends
    X-Stash-Scope to pick the workspace."""
    if req.access not in API_KEY_ACCESS_LEVELS:
        raise HTTPException(status_code=400, detail=f"unknown access level: {req.access}")
    workspace = await _require_active_workspace(scope_user_id)
    key = await create_api_key(scope_user_id, name=req.name, key_type="machine", access=req.access)
    return {"workspace_id": str(workspace["id"]), "api_key": key, "access": req.access}


@router.get("/curator")
async def get_curator(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Everything about the external curator: when it next runs, the exact
    prompt that run will use, which orgs feed the shared wiki, and how the
    recent runs went.

    The prompt is rendered from live state rather than stored, so what this
    shows is literally what the next run sends — including the org list and
    each org's wiki opt-out.
    """
    workspace = await _require_active_workspace(scope_user_id)
    curator = await agent_service.get_or_create_curator(scope_user_id, wiki="external")
    orgs = await org_service.list_orgs(workspace["id"])
    since = curator["curated_through"]
    prompt = prompts.render_external_curator_prompt(
        str(workspace["external_wiki_folder_id"]),
        [
            {
                "name": org["name"],
                "notepad_folder_id": str(org["notepad_folder_id"]),
                "share_wiki": org["share_wiki"],
            }
            for org in orgs
        ],
        since.isoformat() if since else None,
    )
    return {
        "curator": curator,
        "next_run_at": agent_service.next_run_at(curator),
        "prompt": prompt,
        "feeding": [
            {"id": str(o["id"]), "name": o["name"], "external_id": o["external_id"]}
            for o in orgs
            if o["share_wiki"]
        ],
        "opted_out": [
            {"id": str(o["id"]), "name": o["name"], "external_id": o["external_id"]}
            for o in orgs
            if not o["share_wiki"]
        ],
        "runs": await curator_runs(scope_user_id, curator),
    }


@router.post("/curator/run", status_code=202)
async def run_curator_now(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Run the external curator now instead of waiting for tonight's tick.

    The same task the nightly schedule dispatches, minus the due-check — the
    developer is the trigger. Without this there is no way to see the wiki
    build: a developer wiring up their integration would have to wait a day to
    learn whether any of it works.
    """
    from ..services import agent_auth
    from ..tasks.agent_schedules import run_curator_now as dispatch

    await _require_active_workspace(scope_user_id)
    if not await permission_service.is_workspace_member(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    curator = await agent_service.get_or_create_curator(scope_user_id, wiki="external")
    try:
        await agent_auth.resolve(scope_user_id, curator["model_provider"])
    except agent_auth.NeedsAuth:
        raise HTTPException(
            status_code=402,
            detail="Connect a model credential for this workspace before running the curator.",
        )
    except agent_auth.ProviderNotConfigured:
        raise HTTPException(status_code=503, detail="The agent is not configured.")
    dispatch.delay(curator["id"])
    return {"status": "started", "agent_id": curator["id"]}


@orgs_router.get("")
async def list_orgs(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    workspace = await _require_active_workspace(scope_user_id)
    return {
        "workspace": workspace,
        "orgs": await org_service.list_orgs(workspace["id"]),
        "stats": await org_service.workspace_stats(workspace),
    }


async def _org_in_scope(org_id: UUID, scope_user_id: UUID) -> dict:
    org = await org_service.get_org(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Org not found")
    workspace = await workspace_service.get_workspace(org["workspace_id"])
    if workspace["scope_user_id"] != scope_user_id:
        raise HTTPException(status_code=403, detail="Org is not in this scope")
    return org


@orgs_router.get("/{org_id}")
async def get_org_detail(
    org_id: UUID,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """One customer's world: their sessions, their files, their wiki setting."""
    return await org_service.org_detail(await _org_in_scope(org_id, scope_user_id))


@orgs_router.patch("/{org_id}")
async def update_org(
    org_id: UUID,
    req: OrgUpdateRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    await _org_in_scope(org_id, scope_user_id)
    return await org_service.update_org(org_id, name=req.name, share_wiki=req.share_wiki)
