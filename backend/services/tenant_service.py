"""Tenants: External Multiplayer's per-customer boundary.

A developer (e.g. Heavi) runs Stash for *their* customers. Each customer is an
`tenants` row under the developer's workspace, identified by `external_id` — an
id the developer's own backend manages and asserts on every call. Stash
isolates between developers (API keys), not between one developer's tenants:
a request carrying the developer's key may name any of that developer's tenants.

Two memory surfaces hang off this table:
- the workspace's external wiki (`workspaces.external_wiki_folder_id`) —
  cross-tenant, anonymized by the curator, opt-out per tenant via `share_wiki`;
- a per-tenant notepad folder (`tenants.notepad_folder_id`) — non-anonymized,
  visible only through that tenant's own reads and the developer console.

Activating the developer platform on a workspace creates the wiki and
notepads folders; `external_wiki_folder_id IS NOT NULL` is the "developer
platform is active" marker.
"""

from uuid import UUID

from ..database import get_pool
from . import files_tree_service, source_service, workspace_service

_TENANT_COLS_PLAIN = (
    "id, workspace_id, external_id, name, share_wiki, notepad_folder_id, created_at"
)
_TENANT_COLS = (
    "t.id, t.workspace_id, t.external_id, t.name, t.share_wiki, t.notepad_folder_id, t.created_at"
)


async def activate(workspace_id: UUID, created_by: UUID) -> dict:
    """Turn on the developer platform for a workspace: create the external
    wiki and tenant-notepads folders and stamp them on the row. Idempotent."""
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
        owner, "Tenant Notepads", created_by, protected=True
    )
    row = await pool.fetchrow(
        "UPDATE workspaces "
        "SET external_wiki_folder_id = $2, tenant_notepads_folder_id = $3 "
        "WHERE id = $1 AND external_wiki_folder_id IS NULL "
        "RETURNING id, name, domain, scope_user_id, created_by, "
        "         external_wiki_folder_id, tenant_notepads_folder_id, created_at",
        workspace_id,
        wiki["id"],
        notepads["id"],
    )
    if row is None:
        # Lost an activation race — the other winner's folders stand.
        return await workspace_service.get_workspace(workspace_id)
    # The external wiki needs its own curator: the internal one writes the
    # scope's Memory wiki under the opposite privacy rules.
    from . import agent_service

    await agent_service.get_or_create_curator(owner, wiki="external")
    return dict(row)


async def workspace_for_scope(scope_user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, domain, scope_user_id, created_by, "
        "       external_wiki_folder_id, tenant_notepads_folder_id, created_at "
        "FROM workspaces WHERE scope_user_id = $1",
        scope_user_id,
    )
    return dict(row) if row else None


async def get_or_create_tenant(workspace: dict, external_id: str, name: str | None = None) -> dict:
    """Resolve a tenant by the developer's own id, creating it (and its notepad
    folder) on first sight. The name defaults to the external id and is only
    a display label — identity lives on (workspace_id, external_id)."""
    if workspace["external_wiki_folder_id"] is None:
        raise ValueError("developer platform is not active on this workspace — activate it first")
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_TENANT_COLS} FROM tenants t WHERE t.workspace_id = $1 AND t.external_id = $2",
        workspace["id"],
        external_id,
    )
    if row:
        return dict(row)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"tenant:{workspace['id']}:{external_id}",
            )
            row = await conn.fetchrow(
                f"SELECT {_TENANT_COLS} FROM tenants t WHERE t.workspace_id = $1 AND t.external_id = $2",
                workspace["id"],
                external_id,
            )
            if row:
                return dict(row)
            # The folder is named by external_id, not the display name: folders
            # are unique on (owner, parent, name), and two of a developer's
            # customers may well share a display name.
            notepad = await conn.fetchrow(
                "INSERT INTO folders "
                "  (owner_user_id, parent_folder_id, name, created_by, is_protected) "
                "VALUES ($1, $2, $3, $4, true) RETURNING id",
                workspace["scope_user_id"],
                workspace["tenant_notepads_folder_id"],
                external_id,
                workspace["scope_user_id"],
            )
            row = await conn.fetchrow(
                f"INSERT INTO tenants "
                "  (workspace_id, external_id, name, notepad_folder_id) "
                "VALUES ($1, $2, $3, $4) "
                f"RETURNING {_TENANT_COLS_PLAIN}",
                workspace["id"],
                external_id,
                name or external_id,
                notepad["id"],
            )
            return dict(row)


async def find_tenant(workspace_id: UUID, external_id: str) -> dict | None:
    """The tenant by the developer's own id, or None if they have never written
    for that customer."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_TENANT_COLS} FROM tenants t WHERE t.workspace_id = $1 AND t.external_id = $2",
        workspace_id,
        external_id,
    )
    return dict(row) if row else None


async def resolve_tenant_for_scope(owner_user_id: UUID, external_id: str) -> dict:
    """The API-call path: owner scope + developer-asserted tenant id → tenant row.
    Fails loud when the scope is not a developer workspace or the tenant is
    unknown — callers must create tenants through the write path, which names
    them, before reading by tenant."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_TENANT_COLS} FROM tenants t "
        "JOIN workspaces w ON w.id = t.workspace_id "
        "WHERE w.scope_user_id = $1 AND t.external_id = $2",
        owner_user_id,
        external_id,
    )
    if row is None:
        raise ValueError(f"unknown tenant {external_id!r} for this scope")
    return dict(row)


async def list_tenants(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT {_TENANT_COLS}, "
        "       (SELECT count(*) FROM sessions s "
        "        WHERE s.tenant_id = t.id AND s.deleted_at IS NULL) AS session_count, "
        "       (SELECT max(s.started_at) FROM sessions s "
        "        WHERE s.tenant_id = t.id AND s.deleted_at IS NULL) AS last_session_at "
        "FROM tenants t WHERE t.workspace_id = $1 ORDER BY t.created_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def tenants_with_activity_since(workspace_id: UUID, since) -> list[dict]:
    """The tenants a curator run can actually write for: those with events after
    the watermark.

    The prompt names every tenant it lists, so listing all of them makes the
    prompt grow with the size of the customer base rather than with the work in
    front of it. A tenant that said nothing since the last run cannot have
    anything curated for it, so naming it costs tokens and buys nothing — and at
    a few thousand tenants it stops the run working at all.
    """
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT {_TENANT_COLS} FROM tenants t "
        "WHERE t.workspace_id = $1 AND EXISTS ("
        "  SELECT 1 FROM sessions s "
        "  JOIN history_events he ON he.owner_user_id = s.owner_user_id "
        "    AND he.session_id = s.session_id "
        "  WHERE s.tenant_id = t.id AND s.deleted_at IS NULL "
        "    AND ($2::timestamptz IS NULL OR he.created_at > $2)"
        ") ORDER BY t.created_at",
        workspace_id,
        since,
    )
    return [dict(r) for r in rows]


async def external_curator_prompt(workspace: dict, since) -> str:
    """The prompt the external curator will send for this workspace.

    One definition, used by the run and by the console that shows it — the
    console's whole claim is that what it displays is what the run sends, which
    only holds if they build it the same way.
    """
    from . import prompts

    tenants = await tenants_with_activity_since(workspace["id"], since)
    return prompts.render_external_curator_prompt(
        str(workspace["external_wiki_folder_id"]),
        [
            {
                "name": tenant["name"],
                "notepad_folder_id": str(tenant["notepad_folder_id"]),
                "share_wiki": tenant["share_wiki"],
            }
            for tenant in tenants
        ],
        since.isoformat() if since else None,
    )


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
        "SELECT count(*) FROM sessions s JOIN tenants t ON t.id = s.tenant_id "
        "WHERE t.workspace_id = $1 AND s.deleted_at IS NULL",
        workspace["id"],
    )
    return {"wiki_page_count": wiki_page_count, "tenant_session_count": session_count}


async def get_tenant(tenant_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"SELECT {_TENANT_COLS} FROM tenants t WHERE t.id = $1", tenant_id)
    return dict(row) if row else None


async def update_tenant(
    tenant_id: UUID, name: str | None = None, share_wiki: bool | None = None
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        f"UPDATE tenants SET "
        "  name = COALESCE($2, name), "
        "  share_wiki = COALESCE($3, share_wiki) "
        f"WHERE id = $1 RETURNING {_TENANT_COLS_PLAIN}",
        tenant_id,
        name,
        share_wiki,
    )
    if row is None:
        raise ValueError("tenant not found")
    return dict(row)


async def tenant_detail(tenant: dict) -> dict:
    """Everything the console shows about one customer: their transcripts, the
    files their uploads carried, and the notepad the curator writes for them."""
    pool = get_pool()
    sessions = await pool.fetch(
        "SELECT s.session_id, s.agent_name, s.started_at, st.title, "
        "       COUNT(he.id)::int AS event_count, "
        "       COALESCE(MAX(he.created_at), s.started_at) AS last_event_at "
        "FROM sessions s "
        "LEFT JOIN session_titles st "
        "  ON st.owner_user_id = s.owner_user_id AND st.session_id = s.session_id "
        "LEFT JOIN history_events he "
        "  ON he.owner_user_id = s.owner_user_id AND he.session_id = s.session_id "
        "WHERE s.tenant_id = $1 AND s.deleted_at IS NULL "
        "GROUP BY s.session_id, s.agent_name, s.started_at, st.title "
        "ORDER BY last_event_at DESC",
        tenant["id"],
    )
    files = await pool.fetch(
        "SELECT id, name, content_type, size_bytes, created_at "
        "FROM files WHERE tenant_id = $1 AND deleted_at IS NULL "
        "ORDER BY created_at DESC",
        tenant["id"],
    )
    notepad_pages = await pool.fetch(
        "SELECT id, name, updated_at FROM pages "
        "WHERE folder_id = $1 AND deleted_at IS NULL ORDER BY updated_at DESC",
        tenant["notepad_folder_id"],
    )
    workspace = await workspace_service.get_workspace(tenant["workspace_id"])
    sources = await source_service.list_connected_sources(
        workspace["scope_user_id"], tenant_id=tenant["id"]
    )
    return {
        "tenant": tenant,
        "sessions": [dict(r) for r in sessions],
        "files": [dict(r) for r in files],
        "notepad_pages": [dict(r) for r in notepad_pages],
        "sources": sources,
    }
