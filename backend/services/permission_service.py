"""Permission service.

Private by default. Workspace roles grant baseline access: owners/editors can
read and write, viewers can read only. Beyond that, access comes from the
`shares` table: a row grants a principal (a user, or a cartridge) access to an
object. Folder / session-folder shares cascade to contents via the recursive
folder chain. Cartridges are read-only bundles: anyone who can *open* a cartridge
can read every object that cartridge contains (cartridge_items), but a cartridge
never grants write.
"""

from uuid import UUID

from ..database import get_pool

_WORKSPACE_LOOKUP = {
    "table": ("tables", "workspace_id"),
    "file": ("files", "workspace_id"),
    "session": ("sessions", "workspace_id"),
    "session_folder": ("session_folders", "workspace_id"),
    "stash": ("cartridges", "workspace_id"),
    "folder": ("folders", "workspace_id"),
    "page": ("pages", "workspace_id"),
}

_CONTENT_TYPES = {"folder", "page", "session", "table", "file"}
_ROLES_CAN_READ = {"owner", "editor", "viewer"}
_ROLES_CAN_WRITE = {"owner", "editor"}


def _folder_chain_sql(folder_id_expr: str) -> str:
    return (
        "WITH RECURSIVE folder_chain AS ("
        "  SELECT folder_node.id, folder_node.parent_folder_id "
        f"  FROM folders folder_node WHERE folder_node.id = {folder_id_expr}"
        "  UNION ALL"
        "  SELECT parent_folder.id, parent_folder.parent_folder_id FROM folders parent_folder "
        "  JOIN folder_chain c ON parent_folder.id = c.parent_folder_id"
        ") SELECT id FROM folder_chain"
    )


def _item_target_condition(object_type: str, object_alias: str, item_alias: str) -> str:
    """Does a (object_type, object_id) row in `item_alias` (shares OR cartridge_items)
    target the object at `object_alias`? Page/file also match a share/item on any
    ancestor folder (inheritance)."""
    if object_type == "folder":
        folder_chain = _folder_chain_sql(f"{object_alias}.id")
        return (
            f"({item_alias}.object_type = 'folder' "
            f"AND {item_alias}.object_id IN ({folder_chain}))"
        )
    if object_type in ("page", "file", "table"):
        folder_chain = _folder_chain_sql(f"{object_alias}.folder_id")
        return (
            f"(({item_alias}.object_type = '{object_type}' "
            f"AND {item_alias}.object_id = {object_alias}.id) "
            f"OR ({item_alias}.object_type = 'folder' "
            f"AND {object_alias}.folder_id IS NOT NULL "
            f"AND {item_alias}.object_id IN ({folder_chain})))"
        )
    if object_type == "session":
        # A session inherits a share/item on its session folder.
        return (
            f"(({item_alias}.object_type = 'session' "
            f"AND {item_alias}.object_id = {object_alias}.id) "
            f"OR ({item_alias}.object_type = 'session_folder' "
            f"AND {object_alias}.session_folder_id IS NOT NULL "
            f"AND {item_alias}.object_id = {object_alias}.session_folder_id))"
        )
    if object_type in _CONTENT_TYPES:
        return (
            f"({item_alias}.object_type = '{object_type}' "
            f"AND {item_alias}.object_id = {object_alias}.id)"
        )
    return "FALSE"


def readable_content_condition(object_type: str, object_alias: str, user_arg: int) -> str:
    """SQL predicate: may user ${user_arg} READ the content row at object_alias?
    Owner (workspace member) OR a user share (direct/ancestor folder) OR the object
    is in a cartridge the user can open."""
    share_target = _item_target_condition(object_type, object_alias, "content_share")
    ci_target = _item_target_condition(object_type, object_alias, "content_ci")
    return f"""
        (
          EXISTS (
            SELECT 1 FROM workspace_members content_wm
            WHERE content_wm.workspace_id = {object_alias}.workspace_id
              AND content_wm.user_id = ${user_arg}
          )
          OR EXISTS (
            SELECT 1 FROM shares content_share
            WHERE content_share.principal_type = 'user'
              AND content_share.principal_id = ${user_arg}
              AND {share_target}
          )
          OR EXISTS (
            SELECT 1
            FROM cartridge_items content_ci
            JOIN cartridges content_cartridge ON content_cartridge.id = content_ci.cartridge_id
            LEFT JOIN cartridge_members content_cm
              ON content_cm.cartridge_id = content_cartridge.id
             AND content_cm.user_id = ${user_arg}
            WHERE {ci_target}
              AND (
                content_cartridge.public_permission != 'none'
                OR content_cartridge.owner_id = ${user_arg}
                OR content_cm.user_id IS NOT NULL
              )
          )
        )
    """


async def resolve_workspace_id(object_type: str, object_id: UUID) -> UUID | None:
    pool = get_pool()
    if object_type not in _WORKSPACE_LOOKUP:
        return None
    table, col = _WORKSPACE_LOOKUP[object_type]
    row = await pool.fetchrow(f"SELECT {col} AS ws FROM {table} WHERE id = $1", object_id)
    return row["ws"] if row else None


async def _folder_chain_for_page(page_id: UUID) -> list[UUID]:
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
    return [row["id"] for row in rows]


async def _folder_chain_for_file(file_id: UUID) -> list[UUID]:
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT f.id, f.parent_folder_id FROM folders f "
        "  JOIN files fi ON fi.folder_id = f.id WHERE fi.id = $1"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id FROM folders f "
        "  JOIN chain c ON f.id = c.parent_folder_id"
        ") SELECT id FROM chain",
        file_id,
    )
    return [row["id"] for row in rows]


async def _folder_chain_for_table(table_id: UUID) -> list[UUID]:
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT f.id, f.parent_folder_id FROM folders f "
        "  JOIN tables tb ON tb.folder_id = f.id WHERE tb.id = $1"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id FROM folders f "
        "  JOIN chain c ON f.id = c.parent_folder_id"
        ") SELECT id FROM chain",
        table_id,
    )
    return [row["id"] for row in rows]


async def _folder_chain_for_folder(folder_id: UUID) -> list[UUID]:
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
    return [row["id"] for row in rows]


async def _object_targets(object_type: str, object_id: UUID) -> list[tuple[str, UUID]]:
    """The object itself plus any ancestor folders (for inheritance)."""
    if object_type == "folder":
        return [("folder", fid) for fid in await _folder_chain_for_folder(object_id)]
    if object_type == "page":
        return [("page", object_id)] + [
            ("folder", fid) for fid in await _folder_chain_for_page(object_id)
        ]
    if object_type == "file":
        return [("file", object_id)] + [
            ("folder", fid) for fid in await _folder_chain_for_file(object_id)
        ]
    if object_type == "table":
        return [("table", object_id)] + [
            ("folder", fid) for fid in await _folder_chain_for_table(object_id)
        ]
    if object_type == "session":
        pool = get_pool()
        row = await pool.fetchrow("SELECT session_folder_id FROM sessions WHERE id = $1", object_id)
        if row and row["session_folder_id"]:
            return [("session", object_id), ("session_folder", row["session_folder_id"])]
    return [(object_type, object_id)]


async def _user_share_grants(
    object_type: str, object_id: UUID, user_id: UUID, require_write: bool
) -> bool:
    """A user share on the object or any ancestor folder."""
    pool = get_pool()
    for target_type, target_id in await _object_targets(object_type, object_id):
        row = await pool.fetchrow(
            "SELECT permission FROM shares "
            "WHERE principal_type = 'user' AND principal_id = $1 "
            "AND object_type = $2 AND object_id = $3",
            user_id,
            target_type,
            target_id,
        )
        if row and (not require_write or row["permission"] == "write"):
            return True
    return False


async def _containing_cartridges(object_type: str, object_id: UUID) -> list[dict]:
    if object_type not in _CONTENT_TYPES:
        return []
    pool = get_pool()
    rows = []
    for target_type, target_id in await _object_targets(object_type, object_id):
        target_rows = await pool.fetch(
            "SELECT c.id, c.workspace_id, c.owner_id, c.public_permission "
            "FROM cartridges c "
            "JOIN cartridge_items ci ON ci.cartridge_id = c.id "
            "WHERE ci.object_type = $1 AND ci.object_id = $2",
            target_type,
            target_id,
        )
        rows.extend(dict(row) for row in target_rows)
    return rows


async def _cartridge_member_permission(cartridge_id: UUID, user_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT permission FROM cartridge_members WHERE cartridge_id = $1 AND user_id = $2",
        cartridge_id,
        user_id,
    )
    return row["permission"] if row else None


async def _cartridge_open(cartridge: dict, user_id: UUID | None) -> bool:
    """Can the user OPEN this cartridge (read its contents)? Cartridges are
    read-only links: public, owned, or a cartridge member."""
    if cartridge["public_permission"] != "none":
        return True
    if user_id is None:
        return False
    if cartridge["owner_id"] == user_id:
        return True
    return await _cartridge_member_permission(cartridge["id"], user_id) is not None


async def _session_folder_open(
    folder: dict, folder_id: UUID, user_id: UUID | None, require_write: bool
) -> bool:
    """Can the user access this session folder? Public links are read-only.
    Workspace members are granted earlier in check_access."""
    public = folder["public_permission"]
    if not require_write and public != "none":
        return True
    if user_id is None:
        return False
    if folder["owner_user_id"] == user_id:
        return True
    return await _user_share_grants("session_folder", folder_id, user_id, require_write)


async def check_access(
    object_type: str,
    object_id: UUID,
    user_id: UUID | None,
    workspace_id: UUID | None = None,
    require_write: bool = False,
) -> bool:
    if workspace_id is None:
        workspace_id = await resolve_workspace_id(object_type, object_id)

    if user_id is not None and workspace_id is not None:
        role = await get_workspace_role(workspace_id, user_id)
        if require_write and role in _ROLES_CAN_WRITE:
            return True
        if not require_write and role in _ROLES_CAN_READ:
            return True

    # The cartridge bundle itself: gated by cartridge access (read-only).
    if object_type == "stash":
        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT id, workspace_id, owner_id, public_permission FROM cartridges WHERE id = $1",
            object_id,
        )
        if not row:
            return False
        if require_write:
            return row["owner_id"] == user_id
        return await _cartridge_open(dict(row), user_id)

    # A session folder is a shareable bundle: public link, owner, or user share.
    if object_type == "session_folder":
        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT owner_user_id, public_permission, workspace_permission "
            "FROM session_folders WHERE id = $1",
            object_id,
        )
        if not row:
            return False
        return await _session_folder_open(dict(row), object_id, user_id, require_write)

    if object_type not in _CONTENT_TYPES:
        return False

    # Direct or inherited user share.
    if user_id is not None and await _user_share_grants(
        object_type, object_id, user_id, require_write
    ):
        return True

    # Read-only access via a public / shared session folder that contains it.
    if object_type == "session" and not require_write:
        pool = get_pool()
        frow = await pool.fetchrow(
            "SELECT sf.id, sf.owner_user_id, sf.public_permission, sf.workspace_permission "
            "FROM sessions s JOIN session_folders sf ON sf.id = s.session_folder_id "
            "WHERE s.id = $1",
            object_id,
        )
        if frow and await _session_folder_open(dict(frow), frow["id"], user_id, False):
            return True

    # Read-only access via a cartridge that contains the object.
    if not require_write:
        for cartridge in await _containing_cartridges(object_type, object_id):
            if await _cartridge_open(cartridge, user_id):
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
    """'public' if in any public cartridge, 'shared' if shared with anyone,
    else 'private'."""
    pool = get_pool()
    cartridges = await _containing_cartridges(object_type, object_id)
    if any(c["public_permission"] != "none" for c in cartridges):
        return "public"
    shared = await pool.fetchrow(
        "SELECT 1 FROM shares WHERE object_type = $1 AND object_id = $2 LIMIT 1",
        object_type,
        object_id,
    )
    if shared or cartridges:
        return "shared"
    return "private"
