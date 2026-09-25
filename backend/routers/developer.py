"""Developer platform: the console API for External Multiplayer.

Self-serve counterpart to the admin workspace endpoints. A developer activates
the platform (creating a one-man, invite-only workspace when they have none),
mints machine keys on the workspace's scope user, and manages the end users
their product's sessions create. User listing and editing are scope-based like
every other surface: the console sends X-Stash-Scope with the workspace's
scope user id.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..auth import API_KEY_ACCESS_LEVELS, create_api_key, get_current_user, get_scope
from ..database import get_pool
from ..services import (
    agent_service,
    developer_contract_service,
    end_user_service,
    permission_service,
    workspace_service,
)
from .curator_log import curator_runs

router = APIRouter(prefix="/api/v1/me/developer", tags=["developer"])
users_router = APIRouter(prefix="/api/v1/me/users", tags=["developer"])


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
    # None = the key never expires. Days rather than a timestamp so the
    # server's clock is the only clock involved.
    expires_in_days: int | None = Field(None, ge=1, le=3650)


class EndUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    share_skill: bool | None = None


class WikiEndUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    share_wiki: bool | None = None


class CuratorUpdateRequest(BaseModel):
    # Required: a PATCH that omits the field must 422, not silently clear.
    # The empty string is how instructions are cleared on purpose.
    instructions: str = Field(..., max_length=20_000)


async def _require_member_workspace(workspace_id: UUID, user_id: UUID) -> dict:
    workspace = await workspace_service.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not await permission_service.is_workspace_member(workspace["scope_user_id"], user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    return workspace


async def _require_active_workspace(scope_user_id: UUID) -> dict:
    workspace = await end_user_service.workspace_for_scope(scope_user_id)
    if workspace is None or workspace["external_skill_folder_id"] is None:
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
    activated = await end_user_service.activate(workspace["id"], current_user["id"])
    return await developer_contract_service.response(activated["scope_user_id"], activated)


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
    expires_at = (
        datetime.now(UTC) + timedelta(days=req.expires_in_days) if req.expires_in_days else None
    )
    key = await create_api_key(
        scope_user_id, name=req.name, key_type="machine", access=req.access, expires_at=expires_at
    )
    return {
        "workspace_id": str(workspace["id"]),
        "api_key": key,
        "access": req.access,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.get("/keys")
async def list_developer_keys(scope_user_id: UUID = Depends(get_scope)):
    """The workspace's machine keys — names, access, and usage. Key material
    is never returned; a key is shown once, at mint time."""
    await _require_active_workspace(scope_user_id)
    rows = await get_pool().fetch(
        "SELECT id, name, access, created_at, last_used_at, key_prefix, key_suffix, expires_at "
        "FROM user_api_keys "
        "WHERE user_id = $1 AND key_type = 'machine' AND revoked_at IS NULL "
        "ORDER BY created_at DESC",
        scope_user_id,
    )
    return {"keys": [dict(row) for row in rows]}


@router.delete("/keys/{key_id}")
async def revoke_developer_key(key_id: UUID, scope_user_id: UUID = Depends(get_scope)):
    """Revoke one machine key — takes effect on the key's next request.
    Revocation, not deletion: the row stays for the audit trail."""
    await _require_active_workspace(scope_user_id)
    status = await get_pool().execute(
        "UPDATE user_api_keys SET revoked_at = now() "
        "WHERE id = $1 AND user_id = $2 AND key_type = 'machine' AND revoked_at IS NULL",
        key_id,
        scope_user_id,
    )
    if status.endswith(" 0"):
        raise HTTPException(status_code=404, detail="No such active key on this workspace")
    return {"revoked": True}


@router.get("/skill-graph")
async def get_developer_skill_graph(
    scope_user_id: UUID = Depends(get_scope),
):
    """This workspace's shared skill as a graph — the same shape the personal
    Skills graph renders, rooted at the external skill folder instead of
    the curated Skill subtree."""
    from ..services import files_tree_service

    workspace = await _require_active_workspace(scope_user_id)
    folder_id = workspace["external_skill_folder_id"]
    if not folder_id:
        return {"nodes": [], "edges": []}
    return await files_tree_service.skill_graph(
        await files_tree_service.folder_subtree_ids(folder_id)
    )


@router.get("/sessions")
async def list_developer_sessions(scope_user_id: UUID = Depends(get_scope)):
    """Every session the workspace has recorded, newest first, each labelled
    with its end user. User-less rows are the workspace's own agents — the
    curator's runs, mostly."""
    workspace = await _require_active_workspace(scope_user_id)
    return {"sessions": await end_user_service.workspace_sessions(workspace)}


@router.get("/files")
async def list_developer_files(scope_user_id: UUID = Depends(get_scope)):
    """The two kinds of files the platform holds: the shared skill's pages, and
    each user's own material (their skill's pages plus uploaded files)."""
    workspace = await _require_active_workspace(scope_user_id)
    return await developer_contract_service.response(
        scope_user_id, await end_user_service.workspace_files(workspace)
    )


@router.get("/curator")
async def get_curator(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Everything about the external curator: when it next runs, the exact
    prompt that run will use, which users feed the shared skill, and how the
    recent runs went.

    The prompt is rendered from live state rather than stored, so what this
    shows is literally what the next run sends — including the user list and
    each user's skill opt-out.
    """
    workspace = await _require_active_workspace(scope_user_id)
    curator = await agent_service.get_or_create_curator(scope_user_id, skill="external")
    # Every user, for the overview columns; the prompt names only those with
    # material since the watermark, which is all a run can write for.
    end_users = await end_user_service.list_end_users(workspace["id"])
    since = curator["curated_through"]
    prompt = await end_user_service.external_curator_prompt(workspace, since)

    return {
        "curator": curator,
        "next_run_at": agent_service.next_run_at(curator),
        "prompt": prompt,
        # What a backfill would send instead: the same prompt with no
        # watermark, so the run bootstraps from the full history.
        "backfill_prompt": await end_user_service.external_curator_prompt(workspace, None),
        "instructions": curator["system_prompt"],
        "feeding": [
            {"id": str(u["id"]), "name": u["name"], "external_id": u["external_id"]}
            for u in end_users
            if u["share_skill"]
        ],
        "opted_out": [
            {"id": str(u["id"]), "name": u["name"], "external_id": u["external_id"]}
            for u in end_users
            if not u["share_skill"]
        ],
        "runs": await curator_runs(scope_user_id, curator),
    }


@router.patch("/curator")
async def update_curator(
    req: CuratorUpdateRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """The one tunable part of the curator: the workspace's own instructions,
    appended to the rendered prompt on every run. The rendered prompt itself is
    built from live state, which is why it isn't editable directly."""
    await _require_active_workspace(scope_user_id)
    if not await permission_service.is_workspace_member(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    curator = await agent_service.get_or_create_curator(scope_user_id, skill="external")
    updated = await agent_service.set_system_prompt(UUID(curator["id"]), req.instructions)
    return {"instructions": updated["system_prompt"]}


async def _runnable_curator(scope_user_id: UUID, user_id: UUID) -> dict:
    """Authorize a developer's backend curation run."""
    from ..services import agent_auth, scoped_curation_service

    await _require_active_workspace(scope_user_id)
    if not await permission_service.is_workspace_member(scope_user_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    try:
        scoped_curation_service.require_configured()
    except agent_auth.ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await agent_service.get_or_create_curator(scope_user_id, skill="external")


@router.post("/curator/run", status_code=202)
async def run_curator_now(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Run the external curator now instead of waiting for tonight's tick.

    The same task the nightly schedule dispatches, minus the due-check — the
    developer is the trigger. Without this there is no way to see the skill
    build: a developer wiring up their integration would have to wait a day to
    learn whether any of it works.
    """
    from ..tasks.agent_schedules import run_curator_now as dispatch

    curator = await _runnable_curator(scope_user_id, current_user["id"])
    dispatch.delay(curator["id"])
    return {"status": "started", "agent_id": curator["id"]}


@router.post("/curator/backfill", status_code=202)
async def backfill_curator(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Re-run the curator over the workspace's full history.

    The run reads with no watermark, so the prompt bootstraps from everything
    ever uploaded instead of the delta since last night. Pages are updated in
    place — the curator merges rather than duplicates — so this is safe after
    changing the instructions or onboarding real traffic. The stored watermark
    is untouched until the run succeeds: a failed backfill must not have
    thrown away the incremental position.
    """
    from ..tasks.agent_schedules import run_curator_now as dispatch

    curator = await _runnable_curator(scope_user_id, current_user["id"])
    dispatch.delay(curator["id"], full_history=True)
    return {"status": "started", "agent_id": curator["id"]}


@users_router.get("")
async def list_users(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    workspace = await _require_active_workspace(scope_user_id)
    return await developer_contract_service.response(
        scope_user_id,
        {
            "workspace": workspace,
            "users": await end_user_service.list_end_users(workspace["id"]),
            "stats": await end_user_service.workspace_stats(workspace),
        },
    )


async def _end_user_in_scope(user_id: UUID, scope_user_id: UUID) -> dict:
    end_user = await end_user_service.get_end_user(user_id)
    if end_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    workspace = await workspace_service.get_workspace(end_user["workspace_id"])
    if workspace["scope_user_id"] != scope_user_id:
        raise HTTPException(status_code=403, detail="User is not in this scope")
    return end_user


@users_router.get("/{user_id}")
async def get_user_detail(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """One end user's world: their sessions, their files, their skill setting."""
    detail = await end_user_service.end_user_detail(
        await _end_user_in_scope(user_id, scope_user_id)
    )
    return await developer_contract_service.response(scope_user_id, detail)


@users_router.get("/{user_id}/skill-graph")
async def get_user_skill_graph(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """One user's own skill as a graph — the same rendering the shared skill
    gets, rooted at their own skill folder."""
    from ..services import files_tree_service

    end_user = await _end_user_in_scope(user_id, scope_user_id)
    return await files_tree_service.skill_graph(
        await files_tree_service.folder_subtree_ids(end_user["skill_folder_id"])
    )


@users_router.patch("/{user_id}")
async def update_user(
    user_id: UUID,
    req: EndUserUpdateRequest | WikiEndUserUpdateRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    await _end_user_in_scope(user_id, scope_user_id)
    if isinstance(req, WikiEndUserUpdateRequest):
        if not await developer_contract_service.uses_wiki(scope_user_id):
            raise HTTPException(422, "Use share_skill for this workspace")
        share = req.share_wiki
    else:
        share = req.share_skill
    updated = await end_user_service.update_end_user(user_id, name=req.name, share_skill=share)
    return await developer_contract_service.response(scope_user_id, updated)


@router.get("/wiki-graph", include_in_schema=False)
async def get_developer_wiki_graph(scope_user_id: UUID = Depends(get_scope)):
    if not await developer_contract_service.uses_wiki(scope_user_id):
        raise HTTPException(404, "Wiki contract is not enabled")
    return await get_developer_skill_graph(scope_user_id)


@users_router.get("/{user_id}/wiki-graph", include_in_schema=False)
async def get_user_wiki_graph(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    if not await developer_contract_service.uses_wiki(scope_user_id):
        raise HTTPException(404, "Wiki contract is not enabled")
    return await get_user_skill_graph(user_id, current_user, scope_user_id)
