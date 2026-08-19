"""Orgs: External Multiplayer's per-customer boundary.

A developer (e.g. Heavi) runs Stash for *their* customers. Each customer is an
`orgs` row under the developer's workspace, identified by `external_id` — an
id the developer's own backend manages and asserts on every call. Stash
isolates between developers (API keys), not between one developer's orgs:
a request carrying the developer's key may name any of that developer's orgs.

Two memory surfaces hang off this table:
- the workspace's external wiki (`workspaces.external_wiki_folder_id`) —
  cross-org, anonymized by the curator, opt-out per org via `share_wiki`;
- a per-org notepad folder (`orgs.notepad_folder_id`) — non-anonymized,
  visible only through that org's own reads and the developer console.

Activating the developer platform on a workspace creates the wiki and
notepads folders; `external_wiki_folder_id IS NOT NULL` is the "developer
platform is active" marker.
"""

from uuid import UUID

from ..database import get_pool
from . import files_tree_service, workspace_service

_ORG_COLS_PLAIN = "id, workspace_id, external_id, name, share_wiki, notepad_folder_id, created_at"
_ORG_COLS = ", ".join(f"o.{col}" for col in _ORG_COLS_PLAIN.split(", "))


async def activate(workspace_id: UUID, created_by: UUID) -> dict:
    """Turn on the developer platform for a workspace: create the external
    wiki and org-notepads folders and stamp them on the row. Idempotent."""
    pool = get_pool()
    workspace = await workspace_service.get_workspace(workspace_id)
    if workspace is None:
        raise ValueError("workspace not found")
    if workspace["external_wiki_folder_id"] is not None:
        return workspace
    owner = workspace["scope_user_id"]
    wiki = await files_tree_service.create_folder(
        owner, "External Wiki", created_by, protected=True
    )
    notepads = await files_tree_service.create_folder(
        owner, "Org Notepads", created_by, protected=True
    )
    row = await pool.fetchrow(
        "UPDATE workspaces "
        "SET external_wiki_folder_id = $2, org_notepads_folder_id = $3 "
        "WHERE id = $1 AND external_wiki_folder_id IS NULL "
        "RETURNING id, name, domain, scope_user_id, created_by, "
        "         external_wiki_folder_id, org_notepads_folder_id, created_at",
        workspace_id,
        wiki["id"],
        notepads["id"],
    )
    if row is None:
        # Lost an activation race — the other winner's folders stand.
        return await workspace_service.get_workspace(workspace_id)
    return dict(row)


async def workspace_for_scope(scope_user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, domain, scope_user_id, created_by, "
        "       external_wiki_folder_id, org_notepads_folder_id, created_at "
        "FROM workspaces WHERE scope_user_id = $1",
        scope_user_id,
    )
    return dict(row) if row else None


async def get_or_create_org(workspace: dict, external_id: str, name: str | None = None) -> dict:
    """Resolve an org by the developer's own id, creating it (and its notepad
    folder) on first sight. The name defaults to the external id and is only
    a display label — identity lives on (workspace_id, external_id)."""
    if workspace["external_wiki_folder_id"] is None:
        raise ValueError("developer platform is not active on this workspace — activate it first")
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_ORG_COLS} FROM orgs o WHERE o.workspace_id = $1 AND o.external_id = $2",
        workspace["id"],
        external_id,
    )
    if row:
        return dict(row)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"org:{workspace['id']}:{external_id}",
            )
            row = await conn.fetchrow(
                f"SELECT {_ORG_COLS} FROM orgs o WHERE o.workspace_id = $1 AND o.external_id = $2",
                workspace["id"],
                external_id,
            )
            if row:
                return dict(row)
            notepad = await conn.fetchrow(
                "INSERT INTO folders "
                "  (owner_user_id, parent_folder_id, name, created_by, is_protected) "
                "VALUES ($1, $2, $3, $4, true) RETURNING id",
                workspace["scope_user_id"],
                workspace["org_notepads_folder_id"],
                name or external_id,
                workspace["scope_user_id"],
            )
            row = await conn.fetchrow(
                f"INSERT INTO orgs "
                "  (workspace_id, external_id, name, notepad_folder_id) "
                "VALUES ($1, $2, $3, $4) "
                f"RETURNING {_ORG_COLS_PLAIN}",
                workspace["id"],
                external_id,
                name or external_id,
                notepad["id"],
            )
            return dict(row)


async def resolve_org_for_scope(owner_user_id: UUID, external_id: str) -> dict:
    """The API-call path: owner scope + developer-asserted org id → org row.
    Fails loud when the scope is not a developer workspace or the org is
    unknown — callers must create orgs through the write path, which names
    them, before reading by org."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_ORG_COLS} FROM orgs o "
        "JOIN workspaces w ON w.id = o.workspace_id "
        "WHERE w.scope_user_id = $1 AND o.external_id = $2",
        owner_user_id,
        external_id,
    )
    if row is None:
        raise ValueError(f"unknown org {external_id!r} for this scope")
    return dict(row)


async def list_orgs(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT {_ORG_COLS}, "
        "       (SELECT count(*) FROM sessions s "
        "        WHERE s.org_id = o.id AND s.deleted_at IS NULL) AS session_count, "
        "       (SELECT max(s.started_at) FROM sessions s "
        "        WHERE s.org_id = o.id AND s.deleted_at IS NULL) AS last_session_at "
        "FROM orgs o WHERE o.workspace_id = $1 ORDER BY o.created_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def workspace_stats(workspace: dict) -> dict:
    """Console overview numbers: how much the platform has absorbed."""
    pool = get_pool()
    wiki_page_count = await pool.fetchval(
        "WITH RECURSIVE wtree AS ("
        "  SELECT f.id FROM folders f WHERE f.id = $1"
        "  UNION"
        "  SELECT f.id FROM folders f JOIN wtree w ON f.parent_folder_id = w.id"
        ") SELECT count(*) FROM pages p "
        "WHERE p.folder_id IN (SELECT id FROM wtree) AND p.deleted_at IS NULL",
        workspace["external_wiki_folder_id"],
    )
    session_count = await pool.fetchval(
        "SELECT count(*) FROM sessions s JOIN orgs o ON o.id = s.org_id "
        "WHERE o.workspace_id = $1 AND s.deleted_at IS NULL",
        workspace["id"],
    )
    return {"wiki_page_count": wiki_page_count, "org_session_count": session_count}


async def get_org(org_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"SELECT {_ORG_COLS} FROM orgs o WHERE o.id = $1", org_id)
    return dict(row) if row else None


async def update_org(org_id: UUID, name: str | None = None, share_wiki: bool | None = None) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        f"UPDATE orgs SET "
        "  name = COALESCE($2, name), "
        "  share_wiki = COALESCE($3, share_wiki) "
        f"WHERE id = $1 RETURNING {_ORG_COLS_PLAIN}",
        org_id,
        name,
        share_wiki,
    )
    if row is None:
        raise ValueError("org not found")
    return dict(row)
