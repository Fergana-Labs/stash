"""Permission service.

Private by default. Each user owns exactly one scope; they can read and write
everything in it. Beyond their own scope, access comes from the `shares` table:
a row grants a principal access to an object. Folder / session-folder shares
cascade to contents via the recursive folder chain.

A skill is a published folder: publishing makes its folder subtree publicly
readable — never writable.

Scope is the user: every content row carries an `owner_user_id`, and the owner
can do anything in their own scope. A workspace is a scope owned by a dedicated
login-less user; `workspace_members` rows grant members read+write on that
scope's content (never owner powers: shares, sources, publishing stay with the
workspace user itself).
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
    "source": ("user_sources", "owner_user_id"),
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
    if object_type == "source":
        # Connected sources have no container, so only a direct share grants them.
        return (
            f"({share_alias}.object_type = 'source' "
            f"AND {share_alias}.object_id = {object_alias}.id)"
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


# A share satisfies a required level when its own level is >= it (read < comment
# < write). `require` is a trusted internal enum, never user input.
_LEVEL_SHARE_FILTER = {
    "read": "",
    "comment": " AND content_share.permission IN ('comment', 'write')",
    "write": " AND content_share.permission = 'write'",
}

# public_permission ("anyone with the link") values that satisfy each required
# level. A 'write' link grants read+comment+write; 'comment' grants read+comment.
_PUBLIC_LEVELS_FOR = {
    "read": ("read", "comment", "write"),
    "comment": ("comment", "write"),
    "write": ("write",),
}


def _public_permission_condition(object_type: str, object_alias: str, require: str) -> str:
    """SQL predicate: does the per-object public link grant `require`-level access
    to everyone? True when the row's own public_permission is high enough, or —
    cascading like a folder share — any ancestor folder's is. Content rows read
    the ancestor chain from their folder_id; a folder reads it from its own id
    (the recursive CTE includes the folder itself)."""
    levels = ", ".join(f"'{lvl}'" for lvl in _PUBLIC_LEVELS_FOR[require])
    if object_type == "folder":
        chain = _folder_chain_sql(f"{object_alias}.id")
        return (
            f"EXISTS (SELECT 1 FROM folders public_folder "
            f"WHERE public_folder.id IN ({chain}) "
            f"AND public_folder.public_permission IN ({levels}))"
        )
    chain = _folder_chain_sql(f"{object_alias}.folder_id")
    own = f"{object_alias}.public_permission IN ({levels})"
    ancestor = (
        f"({object_alias}.folder_id IS NOT NULL AND EXISTS ("
        f"SELECT 1 FROM folders public_folder "
        f"WHERE public_folder.id IN ({chain}) "
        f"AND public_folder.public_permission IN ({levels})))"
    )
    return f"({own} OR {ancestor})"


def _public_read_container_condition(
    object_type: str, object_alias: str, user_arg: int
) -> str | None:
    """Read-only access a session inherits from its session folder: the folder is
    public, OR the viewer owns the folder — a folder owner reads every session
    filed under it, even sessions they don't own. Content rows use the published-
    skill grant instead; types without a container grant return None."""
    if object_type == "session":
        return (
            f"EXISTS (SELECT 1 FROM session_folders public_sf "
            f"WHERE public_sf.id = {object_alias}.session_folder_id "
            f"AND (public_sf.public_permission <> 'none' "
            f"OR public_sf.owner_user_id = ${user_arg}))"
        )
    return None


def readable_content_condition(
    object_type: str, object_alias: str, user_arg: int, require: str = "read"
) -> str:
    """SQL predicate: may user ${user_arg} access the row at object_alias at the
    `require` level (read < comment < write)? The single source of truth for
    row-level access: owner OR a sufficient user share (direct/ancestor folder)
    OR — for reads only — a public container (published skill folder / public
    session folder). `check_access` executes this same predicate for one row, so
    the SQL filter and the boolean can never disagree."""
    share_target = _share_target_condition(object_type, object_alias, "content_share")
    parts = [
        f"{object_alias}.owner_user_id = ${user_arg}",
        f"EXISTS (SELECT 1 FROM shares content_share "
        f"WHERE content_share.principal_type = 'user' "
        f"AND content_share.principal_id = ${user_arg} "
        f"AND (content_share.expires_at IS NULL OR content_share.expires_at > now()) "
        f"AND {share_target}{_LEVEL_SHARE_FILTER[require]})",
        # Workspace members have read+write on the workspace scope's content,
        # like a 'write' share — so this branch applies at every require level.
        f"EXISTS (SELECT 1 FROM workspaces member_ws "
        f"JOIN workspace_members member_row ON member_row.workspace_id = member_ws.id "
        f"WHERE member_row.user_id = ${user_arg} "
        f"AND member_ws.scope_user_id = {object_alias}.owner_user_id)",
    ]
    # The per-object public link grants read/comment/write to everyone, so it
    # applies at every require level — unlike publishing, which is read-only.
    if object_type in ("page", "file", "table", "folder"):
        parts.append(_public_permission_condition(object_type, object_alias, require))
    if require == "read":
        parts.append(_skill_grant_condition(object_type, object_alias, user_arg))
        public_container = _public_read_container_condition(object_type, object_alias, user_arg)
        if public_container:
            parts.append(public_container)
    return "(" + " OR ".join(parts) + ")"


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
        UNION
        SELECT member_ws.scope_user_id AS id FROM workspaces member_ws
        JOIN workspace_members member_row ON member_row.workspace_id = member_ws.id
        WHERE member_row.user_id = ${user_arg}
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


async def is_workspace_member(scope_user_id: UUID | None, user_id: UUID | None) -> bool:
    """Is `user_id` a member of the workspace whose scope is `scope_user_id`?"""
    if scope_user_id is None or user_id is None:
        return False
    pool = get_pool()
    return bool(
        await pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM workspaces w "
            "JOIN workspace_members m ON m.workspace_id = w.id "
            "WHERE w.scope_user_id = $1 AND m.user_id = $2)",
            scope_user_id,
            user_id,
        )
    )


async def _session_folder_open(
    folder: dict, folder_id: UUID, user_id: UUID | None, require: str
) -> bool:
    """Can the user access this session folder? Public link (read-only),
    owner, workspace member, or an explicit user share."""
    public = folder["public_permission"]
    if require == "read" and public != "none":
        return True
    if user_id is None:
        return False
    if folder["owner_user_id"] == user_id:
        return True
    if await is_workspace_member(folder["owner_user_id"], user_id):
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

    # Connected sources are owner-or-direct-share, executed through the same
    # predicate as content (no folder cascade, no public grant).
    if object_type not in _CONTENT_TYPES and object_type != "source":
        return False

    # A sufficient share, or a public container — the one predicate, executed for
    # this single row. (The owner case already returned above.) user_id may be
    # None (anonymous): the owner/share branches simply never match, leaving only
    # the public read grants. check_access and the list queries now share one
    # definition of access, so they can't drift.
    table = _OWNER_LOOKUP[object_type][0]
    pool = get_pool()
    predicate = readable_content_condition(object_type, "obj", 1, require)
    return bool(
        await pool.fetchval(
            f"SELECT EXISTS (SELECT 1 FROM {table} obj WHERE obj.id = $2 AND {predicate})",
            user_id,
            object_id,
        )
    )


async def _has_public_link(object_type: str, object_id: UUID) -> bool:
    """Does a per-object public link (own row or an ancestor folder) grant
    anyone access? Mirrors the SQL public_permission clause for the Python path."""
    if object_type not in ("page", "file", "table", "folder"):
        return False
    pool = get_pool()
    table = _OWNER_LOOKUP[object_type][0]
    own = await pool.fetchval(f"SELECT public_permission FROM {table} WHERE id = $1", object_id)
    if own and own != "none":
        return True
    ancestor_folder_ids = [
        target_id
        for target_type, target_id in await _object_targets(object_type, object_id)
        if target_type == "folder"
    ]
    if not ancestor_folder_ids:
        return False
    return bool(
        await pool.fetchval(
            "SELECT 1 FROM folders WHERE id = ANY($1::uuid[]) "
            "AND public_permission <> 'none' LIMIT 1",
            ancestor_folder_ids,
        )
    )


async def get_visibility(object_type: str, object_id: UUID) -> str:
    """'public' if reachable by anyone (a public link or a published skill),
    'shared' if shared with a named principal, else 'private'."""
    pool = get_pool()
    if await _containing_skills(object_type, object_id) or await _has_public_link(
        object_type, object_id
    ):
        return "public"
    shared = await pool.fetchrow(
        "SELECT 1 FROM shares WHERE object_type = $1 AND object_id = $2 LIMIT 1",
        object_type,
        object_id,
    )
    if shared:
        return "shared"
    return "private"
