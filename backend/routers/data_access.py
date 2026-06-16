"""Manage publishable (anon) keys and their per-table access policies.

Owner/editor-only. A publishable key is browser-safe and grants nothing on its
own; a policy is a `shares` row (principal_type='api_key') that lets the key
read — or, explicitly, write — one table. Read-only is the default: a write
policy must be asked for.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import create_publishable_key, get_current_user
from ..database import get_pool
from ..services import table_service, workspace_service

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/publishable-keys", tags=["data-access"]
)

POLICY_PERMISSIONS = {"read", "write"}


class KeyCreateRequest(BaseModel):
    name: str = Field("default", min_length=1, max_length=128)


class PolicyRequest(BaseModel):
    table_id: UUID
    permission: str = Field("read", pattern=r"^(read|write)$")


async def _require_owner(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.can_write(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Only workspace owners/editors can manage keys")


async def _require_key(workspace_id: UUID, key_id: UUID) -> None:
    pool = get_pool()
    found = await pool.fetchval(
        "SELECT 1 FROM publishable_keys WHERE id = $1 AND workspace_id = $2", key_id, workspace_id
    )
    if not found:
        raise HTTPException(status_code=404, detail="No such publishable key")


@router.post("", status_code=201)
async def create_key(
    workspace_id: UUID,
    body: KeyCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    await _require_owner(workspace_id, current_user["id"])
    # The raw key is returned exactly once; only its hash is stored.
    key = await create_publishable_key(workspace_id, current_user["id"], body.name)
    return {"name": body.name, "key": key}


@router.get("")
async def list_keys(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    await _require_owner(workspace_id, current_user["id"])
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, created_at, last_used_at, revoked_at FROM publishable_keys "
        "WHERE workspace_id = $1 ORDER BY created_at DESC",
        workspace_id,
    )
    return [dict(r) for r in rows]


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    workspace_id: UUID,
    key_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> None:
    await _require_owner(workspace_id, current_user["id"])
    await _require_key(workspace_id, key_id)
    pool = get_pool()
    await pool.execute("UPDATE publishable_keys SET revoked_at = now() WHERE id = $1", key_id)


@router.put("/{key_id}/policies", status_code=201)
async def set_policy(
    workspace_id: UUID,
    key_id: UUID,
    body: PolicyRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    await _require_owner(workspace_id, current_user["id"])
    await _require_key(workspace_id, key_id)
    table = await table_service.get_table_metadata(body.table_id)
    if not table or table["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="No such table in this workspace")

    pool = get_pool()
    await pool.execute(
        "INSERT INTO shares (workspace_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) "
        "VALUES ($1, 'table', $2, 'api_key', $3, $4, $5) "
        "ON CONFLICT (object_type, object_id, principal_type, principal_id) "
        "DO UPDATE SET permission = EXCLUDED.permission",
        workspace_id,
        body.table_id,
        key_id,
        body.permission,
        current_user["id"],
    )
    return {"table_id": str(body.table_id), "permission": body.permission}


@router.get("/{key_id}/policies")
async def list_policies(
    workspace_id: UUID,
    key_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    await _require_owner(workspace_id, current_user["id"])
    await _require_key(workspace_id, key_id)
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT object_id AS table_id, permission FROM shares "
        "WHERE principal_type = 'api_key' AND principal_id = $1 AND object_type = 'table'",
        key_id,
    )
    return [dict(r) for r in rows]


@router.delete("/{key_id}/policies/{table_id}", status_code=204)
async def remove_policy(
    workspace_id: UUID,
    key_id: UUID,
    table_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> None:
    await _require_owner(workspace_id, current_user["id"])
    await _require_key(workspace_id, key_id)
    pool = get_pool()
    await pool.execute(
        "DELETE FROM shares WHERE principal_type = 'api_key' AND principal_id = $1 "
        "AND object_type = 'table' AND object_id = $2",
        key_id,
        table_id,
    )
