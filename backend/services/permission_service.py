"""Permission service: Google Drive-like access checks for all object types.

Access logic:
1. Workspace owner/admin always has access (bypass all checks).
2. visibility='public' → anyone can read. Write requires share entry.
3. visibility='private' → only users in object_shares.
4. visibility='inherit' (default) → workspace members + object_shares.
"""

from uuid import UUID

from ..database import get_pool


async def check_access(
    object_type: str,
    object_id: UUID,
    user_id: UUID,
    workspace_id: UUID | None = None,
    require_write: bool = False,
) -> bool:
    """Check if a user can access an object. Returns True if allowed."""
    pool = get_pool()

    # Owner of personal (workspace-less) items always has full access
    if workspace_id is None:
        table_map = {
            "chat": ("chats", "creator_id"),
            "notebook": ("notebooks", "created_by"),
            "memory_store": ("memory_stores", "created_by"),
        }
        if object_type in table_map:
            table, col = table_map[object_type]
            row = await pool.fetchrow(
                f"SELECT 1 FROM {table} WHERE id = $1 AND {col} = $2 AND workspace_id IS NULL",
                object_id, user_id,
            )
            if row:
                return True

    # Workspace owner/admin always has access
    if workspace_id:
        role = await get_workspace_role(workspace_id, user_id)
        if role in ("owner", "admin"):
            return True
        if role == "member" and not require_write:
            # Check visibility — 'inherit' means workspace members have read access
            vis = await get_visibility(object_type, object_id)
            if vis == "inherit":
                return True

    # Check visibility
    vis = await get_visibility(object_type, object_id)

    if vis == "public" and not require_write:
        return True

    if vis == "inherit" and workspace_id:
        # Workspace member check (already done above for non-write)
        role = await get_workspace_role(workspace_id, user_id)
        if role is not None:
            if not require_write or role in ("owner", "admin"):
                return True
            # Members can write by default in inherit mode
            return True

    # Check object_shares
    share = await pool.fetchrow(
        "SELECT permission FROM object_shares "
        "WHERE object_type = $1 AND object_id = $2 AND user_id = $3",
        object_type, object_id, user_id,
    )
    if share:
        if not require_write:
            return True
        return share["permission"] in ("write", "admin")

    return False


async def get_workspace_role(workspace_id: UUID, user_id: UUID) -> str | None:
    """Get a user's role in a workspace, or None if not a member."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT role FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id, user_id,
    )
    return row["role"] if row else None


async def is_workspace_member(workspace_id: UUID, user_id: UUID) -> bool:
    return await get_workspace_role(workspace_id, user_id) is not None


async def get_visibility(object_type: str, object_id: UUID) -> str:
    """Get object visibility. Returns 'inherit' if no row exists."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT visibility FROM object_permissions "
        "WHERE object_type = $1 AND object_id = $2",
        object_type, object_id,
    )
    return row["visibility"] if row else "inherit"


async def set_visibility(object_type: str, object_id: UUID, visibility: str) -> None:
    """Set object visibility (inherit/private/public)."""
    pool = get_pool()
    if visibility == "inherit":
        # Remove the row (inherit is default)
        await pool.execute(
            "DELETE FROM object_permissions WHERE object_type = $1 AND object_id = $2",
            object_type, object_id,
        )
    else:
        await pool.execute(
            "INSERT INTO object_permissions (object_type, object_id, visibility) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = $3",
            object_type, object_id, visibility,
        )


async def add_share(
    object_type: str,
    object_id: UUID,
    user_id: UUID,
    permission: str,
    granted_by: UUID,
) -> dict:
    """Grant a user access to an object."""
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO object_shares (object_type, object_id, user_id, permission, granted_by) "
        "VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (object_type, object_id, user_id) DO UPDATE SET permission = $4 "
        "RETURNING *",
        object_type, object_id, user_id, permission, granted_by,
    )
    return dict(row)


async def remove_share(object_type: str, object_id: UUID, user_id: UUID) -> bool:
    """Remove a user's share. Returns True if removed."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM object_shares WHERE object_type = $1 AND object_id = $2 AND user_id = $3",
        object_type, object_id, user_id,
    )
    return result == "DELETE 1"


async def get_shares(object_type: str, object_id: UUID) -> list[dict]:
    """Get all shares for an object."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT os.user_id, u.name AS user_name, os.permission, os.granted_by, os.created_at "
        "FROM object_shares os JOIN users u ON u.id = os.user_id "
        "WHERE os.object_type = $1 AND os.object_id = $2 "
        "ORDER BY os.created_at",
        object_type, object_id,
    )
    return [dict(r) for r in rows]


async def get_permissions(object_type: str, object_id: UUID) -> dict:
    """Get full permissions info for an object (visibility + shares)."""
    vis = await get_visibility(object_type, object_id)
    shares = await get_shares(object_type, object_id)
    return {
        "object_type": object_type,
        "object_id": object_id,
        "visibility": vis,
        "shares": shares,
    }
