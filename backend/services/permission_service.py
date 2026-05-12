"""Permission service: Google Drive-like access checks for all object types.

Access logic:
1. Anonymous viewer (user_id=None) gets read iff visibility is 'link' or 'public'.
2. Workspace owner/admin always has access (bypass all checks).
3. visibility='public'/'link' → anyone can read. Write requires share entry.
4. visibility='private' → only users in object_shares.
5. visibility='inherit' (default) → workspace members + object_shares.

Pages and folders inherit visibility up the folder chain: a private folder
denies access to every page (and every subfolder/page) inside it, even if
the workspace itself is public.
"""

from uuid import UUID

from ..database import get_pool

# Object types that live inside a workspace and have a workspace_id column
# directly. Pages/folders also have workspace_id but their effective
# visibility walks the folder chain first.
_WORKSPACE_LOOKUP = {
    "workspace": ("workspaces", "id"),
    "table": ("tables", "workspace_id"),
    "file": ("files", "workspace_id"),
    "history": ("history_events", "workspace_id"),
    "view": ("views", "workspace_id"),
    "folder": ("folders", "workspace_id"),
    "page": ("pages", "workspace_id"),
}


async def resolve_workspace_id(object_type: str, object_id: UUID) -> UUID | None:
    """Look up the workspace_id for an object."""
    pool = get_pool()
    if object_type in _WORKSPACE_LOOKUP:
        table, col = _WORKSPACE_LOOKUP[object_type]
        row = await pool.fetchrow(f"SELECT {col} AS ws FROM {table} WHERE id = $1", object_id)
        return row["ws"] if row else None
    return None


async def _folder_chain_for_page(page_id: UUID) -> list[UUID]:
    """Folder ids from the page's immediate folder up to the root, in order."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT f.id, f.parent_folder_id FROM folders f "
        "  JOIN pages p ON p.folder_id = f.id WHERE p.id = $1"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id FROM folders f "
        "  JOIN chain c ON f.id = c.parent_folder_id"
        ") SELECT id FROM chain",
        page_id,
    )
    return [r["id"] for r in rows]


async def _folder_chain(folder_id: UUID) -> list[UUID]:
    """The folder itself plus its ancestors, root last."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT id, parent_folder_id FROM folders WHERE id = $1"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id FROM folders f "
        "  JOIN chain c ON f.id = c.parent_folder_id"
        ") SELECT id FROM chain",
        folder_id,
    )
    return [r["id"] for r in rows]


async def _effective_read_visibility(
    object_type: str, object_id: UUID, workspace_id: UUID | None
) -> str:
    """Resolve read inheritance for anonymous/link readers.

    One recursive CTE walks the object → folder chain → workspace path,
    joins to object_permissions, and returns the first non-'inherit'
    visibility. Used to short-circuit N+1 `get_visibility` calls.
    """
    pool = get_pool()

    if object_type == "page":
        row = await pool.fetchrow(
            """
            WITH RECURSIVE chain AS (
                -- The page itself: depth 0, "page" type
                SELECT 0 AS depth, 'page'::text AS object_type, p.id AS object_id,
                       p.folder_id AS next_folder
                FROM pages p WHERE p.id = $1
                UNION ALL
                -- Walk up the folder chain
                SELECT c.depth + 1, 'folder'::text, f.id, f.parent_folder_id
                FROM folders f JOIN chain c ON c.next_folder = f.id
            ),
            with_ws AS (
                SELECT depth, object_type, object_id FROM chain
                UNION ALL
                SELECT (SELECT COUNT(*)+1 FROM chain), 'workspace', $2::uuid
                WHERE $2::uuid IS NOT NULL
            )
            SELECT op.visibility
            FROM with_ws w
            JOIN object_permissions op
              ON op.object_type = w.object_type AND op.object_id = w.object_id
            WHERE op.visibility <> 'inherit'
            ORDER BY w.depth ASC
            LIMIT 1
            """,
            object_id,
            workspace_id,
        )
        return row["visibility"] if row else "inherit"

    if object_type == "folder":
        row = await pool.fetchrow(
            """
            WITH RECURSIVE chain AS (
                SELECT 0 AS depth, id AS object_id, parent_folder_id AS next_folder
                FROM folders WHERE id = $1
                UNION ALL
                SELECT c.depth + 1, f.id, f.parent_folder_id
                FROM folders f JOIN chain c ON c.next_folder = f.id
            ),
            with_ws AS (
                SELECT depth, 'folder'::text AS object_type, object_id FROM chain
                UNION ALL
                SELECT (SELECT COUNT(*)+1 FROM chain), 'workspace', $2::uuid
                WHERE $2::uuid IS NOT NULL
            )
            SELECT op.visibility
            FROM with_ws w
            JOIN object_permissions op
              ON op.object_type = w.object_type AND op.object_id = w.object_id
            WHERE op.visibility <> 'inherit'
            ORDER BY w.depth ASC
            LIMIT 1
            """,
            object_id,
            workspace_id,
        )
        return row["visibility"] if row else "inherit"

    # Non-hierarchical types: just check own visibility, then workspace.
    vis = await get_visibility(object_type, object_id)
    if vis != "inherit":
        return vis
    if object_type == "workspace" or workspace_id is None:
        return "inherit"
    return await get_visibility("workspace", workspace_id)


async def check_access(
    object_type: str,
    object_id: UUID,
    user_id: UUID | None,
    workspace_id: UUID | None = None,
    require_write: bool = False,
) -> bool:
    """Check if a user can access an object. user_id=None means anonymous viewer."""
    pool = get_pool()

    if workspace_id is None:
        workspace_id = await resolve_workspace_id(object_type, object_id)

    if user_id is None:
        if require_write:
            return False
        effective = await _effective_read_visibility(object_type, object_id, workspace_id)
        return effective in ("public", "link")

    role = await get_workspace_role(workspace_id, user_id) if workspace_id else None

    if role in ("owner", "admin"):
        return True

    effective = await _effective_read_visibility(object_type, object_id, workspace_id)
    if effective in ("public", "link") and not require_write:
        return True

    share = await pool.fetchrow(
        "SELECT permission FROM object_shares "
        "WHERE object_type = $1 AND object_id = $2 AND user_id = $3",
        object_type,
        object_id,
        user_id,
    )
    if share:
        if not require_write:
            return True
        return share["permission"] in ("write", "admin")

    # Walk up the folder chain for explicit shares against any ancestor.
    chain: list[tuple[str, UUID]] = []
    if object_type == "page":
        chain = [("folder", fid) for fid in await _folder_chain_for_page(object_id)]
    elif object_type == "folder":
        chain = [("folder", fid) for fid in await _folder_chain(object_id) if fid != object_id]
    for ancestor_type, ancestor_id in chain:
        share = await pool.fetchrow(
            "SELECT permission FROM object_shares "
            "WHERE object_type = $1 AND object_id = $2 AND user_id = $3",
            ancestor_type,
            ancestor_id,
            user_id,
        )
        if share:
            if not require_write:
                return True
            if share["permission"] in ("write", "admin"):
                return True

    # Workspace members fall through to the workspace default for objects
    # whose effective visibility hasn't been pinned down by anything along
    # the chain. Read-only — write still requires a share. We use the
    # effective visibility here (not the direct one) so a private ancestor
    # folder hides its descendants from members without a share.
    if effective in ("inherit", "public", "link") and workspace_id and role is not None:
        if not require_write:
            return True

    return False


async def get_workspace_role(workspace_id: UUID, user_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT role FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    return row["role"] if row else None


async def is_workspace_member(workspace_id: UUID, user_id: UUID) -> bool:
    return await get_workspace_role(workspace_id, user_id) is not None


async def get_visibility(object_type: str, object_id: UUID) -> str:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT visibility FROM object_permissions WHERE object_type = $1 AND object_id = $2",
        object_type,
        object_id,
    )
    return row["visibility"] if row else "inherit"


async def set_visibility(object_type: str, object_id: UUID, visibility: str) -> None:
    pool = get_pool()
    if visibility == "inherit":
        await pool.execute(
            "DELETE FROM object_permissions WHERE object_type = $1 AND object_id = $2",
            object_type,
            object_id,
        )
    else:
        await pool.execute(
            "INSERT INTO object_permissions (object_type, object_id, visibility) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = $3",
            object_type,
            object_id,
            visibility,
        )


async def add_share(
    object_type: str,
    object_id: UUID,
    user_id: UUID,
    permission: str,
    granted_by: UUID,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO object_shares (object_type, object_id, user_id, permission, granted_by) "
        "VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (object_type, object_id, user_id) DO UPDATE SET permission = $4 "
        "RETURNING *",
        object_type,
        object_id,
        user_id,
        permission,
        granted_by,
    )
    return dict(row)


async def remove_share(object_type: str, object_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM object_shares WHERE object_type = $1 AND object_id = $2 AND user_id = $3",
        object_type,
        object_id,
        user_id,
    )
    return result == "DELETE 1"


async def get_shares(object_type: str, object_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT os.user_id, u.name AS user_name, os.permission, os.granted_by, os.created_at "
        "FROM object_shares os JOIN users u ON u.id = os.user_id "
        "WHERE os.object_type = $1 AND os.object_id = $2 "
        "ORDER BY os.created_at",
        object_type,
        object_id,
    )
    return [dict(r) for r in rows]


async def get_permissions(object_type: str, object_id: UUID) -> dict:
    vis = await get_visibility(object_type, object_id)
    shares = await get_shares(object_type, object_id)
    return {
        "object_type": object_type,
        "object_id": object_id,
        "visibility": vis,
        "shares": shares,
    }
