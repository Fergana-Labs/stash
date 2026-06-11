"""Permission service.

Private by default. A user owns everything in their (single, implicit) workspace
— workspace membership == ownership. Beyond that, access comes from the `shares`
table: a row grants a principal access to an object. Principals are a user, or
'public' — the "anyone with the link" grant (sentinel PUBLIC_PRINCIPAL_ID).
Folder / session-folder shares cascade to contents via the recursive folder chain.
Skill access lives in the same table (object_type='skill'). Skills are read-only
bundles: anyone who can *open* a skill can read every object that skill contains
(skill_items), but a skill never grants write to them.
"""

from uuid import UUID

from ..database import get_pool

# principal_id for principal_type='public' rows. A real column value (shares.
# principal_id is NOT NULL) so the one-public-row-per-object UNIQUE holds.
PUBLIC_PRINCIPAL_ID = UUID(int=0)

_WORKSPACE_LOOKUP = {
    "table": ("tables", "workspace_id"),
    "file": ("files", "workspace_id"),
    "session": ("sessions", "workspace_id"),
    "session_folder": ("session_folders", "workspace_id"),
    "skill": ("skills", "workspace_id"),
    "folder": ("folders", "workspace_id"),
    "page": ("pages", "workspace_id"),
}

_CONTENT_TYPES = {"folder", "page", "session", "table", "file"}

# Share permission levels, ordered. A grant satisfies a requirement when its
# level is >= the required level: read < comment < write.
_LEVELS = {"read": 0, "comment": 1, "write": 2}


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
    """Does a (object_type, object_id) row in `item_alias` (shares OR skill_items)
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
    Owner (workspace member) OR a live share — user or public, direct or ancestor
    folder — OR the object is in a skill the user can open. ${user_arg} may
    bind NULL (anonymous): only public grants and public skills match then."""
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
            WHERE ((content_share.principal_type = 'user'
                    AND content_share.principal_id = ${user_arg})
                   OR content_share.principal_type = 'public')
              AND (content_share.expires_at IS NULL OR content_share.expires_at > now())
              AND {share_target}
          )
          OR EXISTS (
            SELECT 1
            FROM skill_items content_ci
            JOIN skills content_skill ON content_skill.id = content_ci.skill_id
            WHERE {ci_target}
              AND (
                content_skill.public_permission != 'none'
                OR content_skill.owner_id = ${user_arg}
                OR EXISTS (
                  SELECT 1 FROM shares skill_share
                  WHERE skill_share.object_type = 'skill'
                    AND skill_share.object_id = content_skill.id
                    AND skill_share.principal_type = 'user'
                    AND skill_share.principal_id = ${user_arg}
                    AND (skill_share.expires_at IS NULL OR skill_share.expires_at > now())
                )
              )
          )
        )
    """


def accessible_workspace_ids_sql(user_arg: int) -> str:
    """Subquery: workspace ids whose content user ${user_arg} can possibly see —
    workspaces they're a member of, plus workspaces that have shared something
    with them. A coarse prefilter only: `readable_content_condition` still narrows
    to the specific shared rows, so widening this set never over-exposes."""
    return f"""(
        SELECT workspace_id FROM workspace_members WHERE user_id = ${user_arg}
        UNION
        SELECT workspace_id FROM shares
        WHERE principal_type = 'user' AND principal_id = ${user_arg}
    )"""


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


async def _share_grants(
    object_type: str, object_id: UUID, user_id: UUID | None, require: str
) -> bool:
    """A live (unexpired) share on the object or any ancestor folder that meets
    the required permission level. Matches the user's own grants plus any
    'public' (anyone with the link) grant, so it works for anonymous viewers."""
    pool = get_pool()
    for target_type, target_id in await _object_targets(object_type, object_id):
        rows = await pool.fetch(
            "SELECT permission FROM shares "
            "WHERE ((principal_type = 'user' AND principal_id = $1) "
            "       OR principal_type = 'public') "
            "AND object_type = $2 AND object_id = $3 "
            "AND (expires_at IS NULL OR expires_at > now())",
            user_id,
            target_type,
            target_id,
        )
        if any(_LEVELS[row["permission"]] >= _LEVELS[require] for row in rows):
            return True
    return False


async def _containing_skills(object_type: str, object_id: UUID) -> list[dict]:
    if object_type not in _CONTENT_TYPES:
        return []
    pool = get_pool()
    rows = []
    for target_type, target_id in await _object_targets(object_type, object_id):
        target_rows = await pool.fetch(
            "SELECT c.id, c.workspace_id, c.owner_id, c.public_permission "
            "FROM skills c "
            "JOIN skill_items ci ON ci.skill_id = c.id "
            "WHERE ci.object_type = $1 AND ci.object_id = $2",
            target_type,
            target_id,
        )
        rows.extend(dict(row) for row in target_rows)
    return rows


async def _skill_open(skill: dict, user_id: UUID | None) -> bool:
    """Can the user OPEN this skill (read its contents)? Skills are
    read-only links: public, owned, or shared with the user."""
    if skill["public_permission"] != "none":
        return True
    if user_id is None:
        return False
    if skill["owner_id"] == user_id:
        return True
    return await _share_grants("skill", skill["id"], user_id, "read")


async def _session_folder_open(
    folder: dict, folder_id: UUID, user_id: UUID | None, require: str
) -> bool:
    """Can the user access this session folder? Mirrors _skill_open: public
    link, owner, or an explicit user share. Workspace members are granted earlier
    in check_access (the workspace is the trust boundary)."""
    public = folder["public_permission"]
    if require == "read" and public != "none":
        return True
    if require == "write" and public == "write":
        return True
    if user_id is None:
        return False
    if folder["owner_user_id"] == user_id:
        return True
    return await _share_grants("session_folder", folder_id, user_id, require)


async def check_access(
    object_type: str,
    object_id: UUID,
    user_id: UUID | None,
    workspace_id: UUID | None = None,
    require: str = "read",
) -> bool:
    """`require` is the permission level needed: read < comment < write."""
    if workspace_id is None:
        workspace_id = await resolve_workspace_id(object_type, object_id)

    # Owner = the (single) workspace member. Full read/write.
    if (
        user_id is not None
        and workspace_id is not None
        and await is_workspace_member(workspace_id, user_id)
    ):
        return True

    # The skill bundle itself: gated by skill access (read-only).
    if object_type == "skill":
        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT id, workspace_id, owner_id, public_permission FROM skills WHERE id = $1",
            object_id,
        )
        if not row:
            return False
        if require != "read":
            if row["owner_id"] == user_id:
                return True
            return user_id is not None and await _share_grants(
                "skill", object_id, user_id, require
            )
        return await _skill_open(dict(row), user_id)

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
        return await _session_folder_open(dict(row), object_id, user_id, require)

    if object_type not in _CONTENT_TYPES:
        return False

    # Direct or inherited share — the user's own, or a public (anyone with the
    # link) grant, which also covers anonymous viewers.
    if await _share_grants(object_type, object_id, user_id, require):
        return True

    # Read-only access via a public / shared session folder that contains it.
    if object_type == "session" and require == "read":
        pool = get_pool()
        frow = await pool.fetchrow(
            "SELECT sf.id, sf.owner_user_id, sf.public_permission, sf.workspace_permission "
            "FROM sessions s JOIN session_folders sf ON sf.id = s.session_folder_id "
            "WHERE s.id = $1",
            object_id,
        )
        if frow and await _session_folder_open(dict(frow), frow["id"], user_id, "read"):
            return True

    # Read-only access via a skill that contains the object.
    if require == "read":
        for skill in await _containing_skills(object_type, object_id):
            if await _skill_open(skill, user_id):
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
    """'public' if anyone with the link can see it (a public grant, direct or
    inherited, or a public skill), 'shared' if shared with anyone, else
    'private'."""
    pool = get_pool()
    if await _share_grants(object_type, object_id, None, "read"):
        return "public"
    skills = await _containing_skills(object_type, object_id)
    if any(c["public_permission"] != "none" for c in skills):
        return "public"
    shared = await pool.fetchrow(
        "SELECT 1 FROM shares WHERE object_type = $1 AND object_id = $2 LIMIT 1",
        object_type,
        object_id,
    )
    if shared or skills:
        return "shared"
    return "private"
