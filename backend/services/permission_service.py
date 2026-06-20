"""Permission service.

Private by default. Each user owns exactly one scope; they can read and write
everything in it. Beyond their own scope, access comes from the `shares` table:
a row grants a principal access to an object. Folder / session-folder shares
cascade to contents via the recursive folder chain.

A skill is a published folder: publishing makes its folder subtree publicly
readable — never writable.

Scope is the user: every content row carries an `owner_user_id`, and the owner
can do anything in their own scope.
"""

from uuid import UUID

from ..database import get_pool

_OWNER_LOOKUP = {
    "table": ("tables", "owner_user_id"),
    "file": ("files", "owner_user_id"),
    "session": ("sessions", "owner_user_id"),
    "session_folder": ("session_folders", "owner_user_id"),
    "skill": ("skills", "owner_user_id"),
    "folder": ("folders", "owner_user_id"),
    "page": ("pages", "owner_user_id"),
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


def _share_target_condition(object_type: str, object_alias: str, share_alias: str) -> str:
    """Does a (object_type, object_id) share row in `share_alias` target the
    object at `object_alias`? Page/file/table also match a share on any
    ancestor folder (inheritance)."""
    if object_type == "folder":
        folder_chain = _folder_chain_sql(f"{object_alias}.id")
        return (
            f"({share_alias}.object_type = 'folder' "
            f"AND {share_alias}.object_id IN ({folder_chain}))"
        )
    if object_type in ("page", "file", "table"):
        folder_chain = _folder_chain_sql(f"{object_alias}.folder_id")
        return (
            f"(({share_alias}.object_type = '{object_type}' "
            f"AND {share_alias}.object_id = {object_alias}.id) "
            f"OR ({share_alias}.object_type = 'folder' "
            f"AND {object_alias}.folder_id IS NOT NULL "
            f"AND {share_alias}.object_id IN ({folder_chain})))"
        )
    if object_type == "session":
        # A session inherits a share on its session folder.
        return (
            f"(({share_alias}.object_type = 'session' "
            f"AND {share_alias}.object_id = {object_alias}.id) "
            f"OR ({share_alias}.object_type = 'session_folder' "
            f"AND {object_alias}.session_folder_id IS NOT NULL "
            f"AND {share_alias}.object_id = {object_alias}.session_folder_id))"
        )
    if object_type in _CONTENT_TYPES:
        return (
            f"({share_alias}.object_type = '{object_type}' "
            f"AND {share_alias}.object_id = {object_alias}.id)"
        )
    return "FALSE"


def _skill_grant_condition(object_type: str, object_alias: str, user_arg: int) -> str:
    """A published skill on an ancestor folder grants READ to everyone —
    publishing IS the public grant. Person shares ride the shares branch.
    Sessions never live in folders, so no skill clause."""
    _ = user_arg
    if object_type == "folder":
        folder_chain = _folder_chain_sql(f"{object_alias}.id")
    elif object_type in ("page", "file", "table"):
        folder_chain = _folder_chain_sql(f"{object_alias}.folder_id")
    else:
        return "FALSE"
    guard = (
        f"{object_alias}.folder_id IS NOT NULL AND "
        if object_type in ("page", "file", "table")
        else ""
    )
    return f"""
        ({guard}EXISTS (
          SELECT 1 FROM skills content_skill
          WHERE content_skill.folder_id IN ({folder_chain})
        ))
    """


def readable_content_condition(object_type: str, object_alias: str, user_arg: int) -> str:
    """SQL predicate: may user ${user_arg} READ the content row at object_alias?
    Owner OR a user share (direct/ancestor folder) OR the object sits inside the
    folder of a skill the user can open."""
    share_target = _share_target_condition(object_type, object_alias, "content_share")
    skill_grant = _skill_grant_condition(object_type, object_alias, user_arg)
    return f"""
        (
          {object_alias}.owner_user_id = ${user_arg}
          OR EXISTS (
            SELECT 1 FROM shares content_share
            WHERE content_share.principal_type = 'user'
              AND content_share.principal_id = ${user_arg}
              AND (content_share.expires_at IS NULL OR content_share.expires_at > now())
              AND {share_target}
          )
          OR {skill_grant}
        )
    """


def accessible_scope_ids_sql(user_arg: int) -> str:
    """Subquery: owner ids whose content user ${user_arg} can possibly see —
    themselves, plus owners who have shared something with them. A coarse
    prefilter only: `readable_content_condition` still narrows to the specific
    shared rows, so widening this set never over-exposes."""
    return f"""(
        SELECT ${user_arg}::uuid AS id
        UNION
        SELECT owner_user_id AS id FROM shares
        WHERE principal_type = 'user' AND principal_id = ${user_arg}
    )"""


async def resolve_owner_user_id(object_type: str, object_id: UUID) -> UUID | None:
    pool = get_pool()
    if object_type not in _OWNER_LOOKUP:
        return None
    table, col = _OWNER_LOOKUP[object_type]
    row = await pool.fetchrow(f"SELECT {col} AS owner FROM {table} WHERE id = $1", object_id)
    return row["owner"] if row else None


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
    object_type: str, object_id: UUID, user_id: UUID, require: str
) -> bool:
    """A live (unexpired) user share on the object or any ancestor folder that
    meets the required permission level."""
    pool = get_pool()
    for target_type, target_id in await _object_targets(object_type, object_id):
        row = await pool.fetchrow(
            "SELECT permission FROM shares "
            "WHERE principal_type = 'user' AND principal_id = $1 "
            "AND object_type = $2 AND object_id = $3 "
            "AND (expires_at IS NULL OR expires_at > now())",
            user_id,
            target_type,
            target_id,
        )
        if row and _LEVELS[row["permission"]] >= _LEVELS[require]:
            return True
    return False


async def _containing_skills(object_type: str, object_id: UUID) -> list[dict]:
    """Published skills whose folder is the object or one of its ancestors."""
    if object_type not in _CONTENT_TYPES:
        return []
    ancestor_folder_ids = [
        target_id
        for target_type, target_id in await _object_targets(object_type, object_id)
        if target_type == "folder"
    ]
    if not ancestor_folder_ids:
        return []
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, owner_user_id, owner_id FROM skills WHERE folder_id = ANY($1::uuid[])",
        ancestor_folder_ids,
    )
    return [dict(row) for row in rows]


async def _session_folder_open(
    folder: dict, folder_id: UUID, user_id: UUID | None, require: str
) -> bool:
    """Can the user access this session folder? Public link (read-only),
    owner, or an explicit user share."""
    public = folder["public_permission"]
    if require == "read" and public != "none":
        return True
    if user_id is None:
        return False
    if folder["owner_user_id"] == user_id:
        return True
    return await _user_share_grants("session_folder", folder_id, user_id, require)


async def check_access(
    object_type: str,
    object_id: UUID,
    user_id: UUID | None,
    owner_user_id: UUID | None = None,
    require: str = "read",
) -> bool:
    """`require` is the permission level needed: read < comment < write."""
    if owner_user_id is None:
        owner_user_id = await resolve_owner_user_id(object_type, object_id)

    # The owner can do anything in their own scope.
    if user_id is not None and owner_user_id is not None and owner_user_id == user_id:
        return True

    # The publish record itself: existence == publicly readable; owner manages.
    if object_type == "skill":
        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT id, owner_id FROM skills WHERE id = $1",
            object_id,
        )
        if not row:
            return False
        if require != "read":
            return row["owner_id"] == user_id
        return True

    # A session folder is a shareable bundle: public link, owner, or user share.
    if object_type == "session_folder":
        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT owner_user_id, public_permission FROM session_folders WHERE id = $1",
            object_id,
        )
        if not row:
            return False
        return await _session_folder_open(dict(row), object_id, user_id, require)

    if object_type not in _CONTENT_TYPES:
        return False

    # Direct or inherited user share.
    if user_id is not None and await _user_share_grants(object_type, object_id, user_id, require):
        return True

    # Read-only access via a public / shared session folder that contains it.
    if object_type == "session" and require == "read":
        pool = get_pool()
        frow = await pool.fetchrow(
            "SELECT sf.id, sf.owner_user_id, sf.public_permission "
            "FROM sessions s JOIN session_folders sf ON sf.id = s.session_folder_id "
            "WHERE s.id = $1",
            object_id,
        )
        if frow and await _session_folder_open(dict(frow), frow["id"], user_id, "read"):
            return True

    # Read-only access via a published skill that contains the object.
    if require == "read" and await _containing_skills(object_type, object_id):
        return True

    return False


async def get_visibility(object_type: str, object_id: UUID) -> str:
    """'public' if in any public skill, 'shared' if shared with anyone,
    else 'private'."""
    pool = get_pool()
    skills = await _containing_skills(object_type, object_id)
    if skills:
        return "public"
    shared = await pool.fetchrow(
        "SELECT 1 FROM shares WHERE object_type = $1 AND object_id = $2 LIMIT 1",
        object_type,
        object_id,
    )
    if shared or skills:
        return "shared"
    return "private"
