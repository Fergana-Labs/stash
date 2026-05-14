"""Permission service for workspace content objects."""

from uuid import UUID

from ..database import get_pool

# Object types that live inside a workspace and have a workspace_id column directly.
_WORKSPACE_LOOKUP = {
    "table": ("tables", "workspace_id"),
    "file": ("files", "workspace_id"),
    "history": ("history_events", "workspace_id"),
    "session": ("sessions", "workspace_id"),
    "stash": ("stashes", "workspace_id"),
    "folder": ("folders", "workspace_id"),
    "page": ("pages", "workspace_id"),
}

_TAG_OBJECT_TYPES = {"folder", "page", "session", "table", "file", "history"}


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


async def _privacy_targets(object_type: str, object_id: UUID) -> list[tuple[str, UUID]]:
    if object_type == "page":
        return [("page", object_id)] + [
            ("folder", folder_id) for folder_id in await _folder_chain_for_page(object_id)
        ]
    if object_type == "folder":
        return [("folder", folder_id) for folder_id in await _folder_chain(object_id)]
    if object_type == "session":
        return [("session", object_id)]
    if object_type in {"table", "file", "history"}:
        return [(object_type, object_id)]
    return []


async def _effective_privacy_tags(object_type: str, object_id: UUID) -> list[dict]:
    pool = get_pool()
    tags: list[dict] = []
    for target_type, target_id in await _privacy_targets(object_type, object_id):
        rows = await pool.fetch(
            "SELECT pt.id, pt.workspace_id, pt.name, pt.access "
            "FROM privacy_tag_objects pto "
            "JOIN privacy_tags pt ON pt.id = pto.tag_id "
            "WHERE pto.object_type = $1 AND pto.object_id = $2 "
            "ORDER BY pt.name",
            target_type,
            target_id,
        )
        tags.extend(dict(row) for row in rows)
    return tags


async def _tag_member_permission(tag_id: UUID, user_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT permission FROM privacy_tag_members WHERE tag_id = $1 AND user_id = $2",
        tag_id,
        user_id,
    )
    return row["permission"] if row else None


async def _privacy_tag_allows(tag: dict, user_id: UUID | None, require_write: bool) -> bool:
    access = tag["access"]
    if user_id is None:
        return access == "public" and not require_write

    if access == "public":
        return not require_write
    if access == "workspace":
        if require_write:
            return False
        return await is_workspace_member(tag["workspace_id"], user_id)

    permission = await _tag_member_permission(tag["id"], user_id)
    if not permission:
        return False
    if not require_write:
        return True
    return permission in ("write", "admin")


async def _check_tag_access(
    object_type: str,
    object_id: UUID,
    user_id: UUID | None,
    workspace_id: UUID | None,
    require_write: bool,
) -> bool:
    if user_id is not None:
        role = await get_workspace_role(workspace_id, user_id) if workspace_id else None
        if role in ("owner", "admin"):
            return True

    tags = await _effective_privacy_tags(object_type, object_id)
    if not tags:
        if user_id is None or require_write:
            return False
        return bool(workspace_id and await is_workspace_member(workspace_id, user_id))

    for tag in tags:
        if not await _privacy_tag_allows(tag, user_id, require_write):
            return False
    return True


async def check_access(
    object_type: str,
    object_id: UUID,
    user_id: UUID | None,
    workspace_id: UUID | None = None,
    require_write: bool = False,
) -> bool:
    """Check if a user can access an object. user_id=None means anonymous viewer."""
    if workspace_id is None:
        workspace_id = await resolve_workspace_id(object_type, object_id)

    if object_type in _TAG_OBJECT_TYPES:
        return await _check_tag_access(object_type, object_id, user_id, workspace_id, require_write)

    if user_id is None:
        return False

    role = await get_workspace_role(workspace_id, user_id) if workspace_id else None
    if role in ("owner", "admin"):
        return True
    return bool(role and not require_write)


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
    if object_type not in _TAG_OBJECT_TYPES:
        raise ValueError(f"Unsupported privacy tag object type: {object_type}")

    tags = await _effective_privacy_tags(object_type, object_id)
    if not tags:
        return "inherit"
    if all(tag["access"] == "public" for tag in tags):
        return "public"
    return "private"


async def set_visibility(object_type: str, object_id: UUID, visibility: str) -> None:
    await set_privacy_visibility(object_type, object_id, visibility)


async def set_privacy_visibility(
    object_type: str,
    object_id: UUID,
    visibility: str,
    created_by: UUID | None = None,
) -> None:
    if object_type not in _TAG_OBJECT_TYPES:
        raise ValueError(f"Unsupported privacy tag object type: {object_type}")
    if visibility not in {"inherit", "private", "link", "public"}:
        raise ValueError(f"Unsupported visibility: {visibility}")

    pool = get_pool()
    await pool.execute(
        "DELETE FROM privacy_tag_objects WHERE object_type = $1 AND object_id = $2",
        object_type,
        object_id,
    )
    if visibility == "inherit":
        return

    workspace_id = await resolve_workspace_id(object_type, object_id)
    if workspace_id is None:
        raise ValueError("Object not found")

    access = "public" if visibility in ("link", "public") else "members"
    tag = await pool.fetchrow(
        "INSERT INTO privacy_tags (workspace_id, name, access, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (workspace_id, name) DO UPDATE SET access = $3, updated_at = now() "
        "RETURNING id",
        workspace_id,
        f"{object_type}:{object_id}:{visibility}",
        access,
        created_by,
    )
    await pool.execute(
        "INSERT INTO privacy_tag_objects (tag_id, object_type, object_id) "
        "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
        tag["id"],
        object_type,
        object_id,
    )
    if visibility == "private" and created_by is not None:
        await pool.execute(
            "INSERT INTO privacy_tag_members (tag_id, user_id, permission) "
            "VALUES ($1, $2, 'admin') "
            "ON CONFLICT (tag_id, user_id) DO UPDATE SET permission = 'admin'",
            tag["id"],
            created_by,
        )


async def add_share(
    object_type: str,
    object_id: UUID,
    user_id: UUID,
    permission: str,
    granted_by: UUID,
) -> dict:
    pool = get_pool()
    if object_type in _TAG_OBJECT_TYPES:
        workspace_id = await resolve_workspace_id(object_type, object_id)
        if workspace_id is None:
            raise ValueError("Object not found")
        tag = await pool.fetchrow(
            "SELECT pt.id FROM privacy_tags pt "
            "JOIN privacy_tag_objects pto ON pto.tag_id = pt.id "
            "WHERE pto.object_type = $1 AND pto.object_id = $2 AND pt.access = 'members' "
            "ORDER BY pt.created_at LIMIT 1",
            object_type,
            object_id,
        )
        if not tag:
            tag = await pool.fetchrow(
                "INSERT INTO privacy_tags (workspace_id, name, access, created_by) "
                "VALUES ($1, $2, 'members', $3) "
                "ON CONFLICT (workspace_id, name) DO UPDATE SET updated_at = now() "
                "RETURNING id",
                workspace_id,
                f"{object_type}:{object_id}:shared",
                granted_by,
            )
            await pool.execute(
                "INSERT INTO privacy_tag_objects (tag_id, object_type, object_id) "
                "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                tag["id"],
                object_type,
                object_id,
            )
        row = await pool.fetchrow(
            "INSERT INTO privacy_tag_members (tag_id, user_id, permission) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (tag_id, user_id) DO UPDATE SET permission = $3 "
            "RETURNING $2::uuid AS user_id, permission, $4::uuid AS granted_by, created_at",
            tag["id"],
            user_id,
            permission,
            granted_by,
        )
        return dict(row)

    raise ValueError(f"Unsupported privacy tag object type: {object_type}")


async def remove_share(object_type: str, object_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    if object_type in _TAG_OBJECT_TYPES:
        result = await pool.execute(
            "DELETE FROM privacy_tag_members ptm "
            "USING privacy_tag_objects pto "
            "WHERE ptm.tag_id = pto.tag_id "
            "AND pto.object_type = $1 AND pto.object_id = $2 AND ptm.user_id = $3",
            object_type,
            object_id,
            user_id,
        )
        return result != "DELETE 0"

    raise ValueError(f"Unsupported privacy tag object type: {object_type}")


async def get_shares(object_type: str, object_id: UUID) -> list[dict]:
    pool = get_pool()
    if object_type in _TAG_OBJECT_TYPES:
        rows = await pool.fetch(
            "SELECT ptm.user_id, u.name AS user_name, ptm.permission, "
            "pt.created_by AS granted_by, ptm.created_at "
            "FROM privacy_tag_members ptm "
            "JOIN privacy_tag_objects pto ON pto.tag_id = ptm.tag_id "
            "JOIN privacy_tags pt ON pt.id = ptm.tag_id "
            "JOIN users u ON u.id = ptm.user_id "
            "WHERE pto.object_type = $1 AND pto.object_id = $2 "
            "ORDER BY ptm.created_at",
            object_type,
            object_id,
        )
        return [dict(r) for r in rows]

    raise ValueError(f"Unsupported privacy tag object type: {object_type}")


async def get_permissions(object_type: str, object_id: UUID) -> dict:
    vis = await get_visibility(object_type, object_id)
    shares = await get_shares(object_type, object_id)
    tags = []
    if object_type in _TAG_OBJECT_TYPES:
        tags = [
            {
                "id": tag["id"],
                "name": tag["name"],
                "access": tag["access"],
            }
            for tag in await _effective_privacy_tags(object_type, object_id)
        ]
    return {
        "object_type": object_type,
        "object_id": object_id,
        "visibility": vis,
        "shares": shares,
        "tags": tags,
    }
