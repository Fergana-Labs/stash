"""End users: External Multiplayer's per-customer boundary.

A developer (e.g. Heavi) runs Stash for *their* users. Each end user — a
company, or one person — is an `end_users` row under the developer's
workspace, identified by `external_id`: an id the developer's own backend
manages and asserts on every call. Stash isolates between developers (API
keys), not between one developer's users: a request carrying the developer's
key may name any of that developer's users.

Naming: the wire says `user_id` — from the caller's side there is only one
kind of user, theirs. Inside Stash "user" means an account, so the schema and
this module say end_user. Nothing anywhere says tenant.

Two memory surfaces hang off this table:
- the workspace's external wiki (`workspaces.external_wiki_folder_id`) —
  cross-user, anonymized by the curator, opt-out per user via `share_wiki`;
- a per-user notepad folder (`end_users.notepad_folder_id`) — non-anonymized,
  visible only through that user's own reads and the developer console.

Activating the developer platform on a workspace creates the wiki and
notepads folders; `external_wiki_folder_id IS NOT NULL` is the "developer
platform is active" marker.
"""

from uuid import UUID

from ..database import get_pool
from . import files_tree_service, source_service, workspace_service

_END_USER_COLS_PLAIN = (
    "id, workspace_id, external_id, name, share_wiki, notepad_folder_id, created_at"
)
_END_USER_COLS = (
    "eu.id, eu.workspace_id, eu.external_id, eu.name, eu.share_wiki, "
    "eu.notepad_folder_id, eu.created_at"
)


async def activate(workspace_id: UUID, created_by: UUID) -> dict:
    """Turn on the developer platform for a workspace: create the external
    wiki and user-notepads folders and stamp them on the row. Idempotent."""
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
        owner, "User Notepads", created_by, protected=True
    )
    row = await pool.fetchrow(
        "UPDATE workspaces "
        "SET external_wiki_folder_id = $2, end_user_notepads_folder_id = $3 "
        "WHERE id = $1 AND external_wiki_folder_id IS NULL "
        "RETURNING id, name, domain, scope_user_id, created_by, "
        "         external_wiki_folder_id, end_user_notepads_folder_id, created_at",
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
        "       external_wiki_folder_id, end_user_notepads_folder_id, created_at "
        "FROM workspaces WHERE scope_user_id = $1",
        scope_user_id,
    )
    return dict(row) if row else None


async def get_or_create_end_user(
    workspace: dict, external_id: str, name: str | None = None
) -> dict:
    """Resolve an end user by the developer's own id, creating them (and their
    notepad folder) on first sight. The name defaults to the external id and is
    only a display label — identity lives on (workspace_id, external_id)."""
    if workspace["external_wiki_folder_id"] is None:
        raise ValueError("developer platform is not active on this workspace — activate it first")
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_END_USER_COLS} FROM end_users eu "
        "WHERE eu.workspace_id = $1 AND eu.external_id = $2",
        workspace["id"],
        external_id,
    )
    if row:
        return dict(row)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"end_user:{workspace['id']}:{external_id}",
            )
            row = await conn.fetchrow(
                f"SELECT {_END_USER_COLS} FROM end_users eu "
                "WHERE eu.workspace_id = $1 AND eu.external_id = $2",
                workspace["id"],
                external_id,
            )
            if row:
                return dict(row)
            # The folder is named by external_id, not the display name: folders
            # are unique on (owner, parent, name), and two of a developer's
            # users may well share a display name.
            notepad = await conn.fetchrow(
                "INSERT INTO folders "
                "  (owner_user_id, parent_folder_id, name, created_by, is_protected) "
                "VALUES ($1, $2, $3, $4, true) RETURNING id",
                workspace["scope_user_id"],
                workspace["end_user_notepads_folder_id"],
                external_id,
                workspace["scope_user_id"],
            )
            row = await conn.fetchrow(
                f"INSERT INTO end_users "
                "  (workspace_id, external_id, name, notepad_folder_id) "
                "VALUES ($1, $2, $3, $4) "
                f"RETURNING {_END_USER_COLS_PLAIN}",
                workspace["id"],
                external_id,
                name or external_id,
                notepad["id"],
            )
            return dict(row)


async def find_end_user(workspace_id: UUID, external_id: str) -> dict | None:
    """The end user by the developer's own id, or None if they have never
    written for them."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_END_USER_COLS} FROM end_users eu "
        "WHERE eu.workspace_id = $1 AND eu.external_id = $2",
        workspace_id,
        external_id,
    )
    return dict(row) if row else None


async def resolve_end_user_for_scope(owner_user_id: UUID, external_id: str) -> dict:
    """The API-call path: owner scope + developer-asserted user id → end_users
    row. Fails loud when the scope is not a developer workspace or the user is
    unknown — callers must create users through the write path, which names
    them, before reading by user."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_END_USER_COLS} FROM end_users eu "
        "JOIN workspaces w ON w.id = eu.workspace_id "
        "WHERE w.scope_user_id = $1 AND eu.external_id = $2",
        owner_user_id,
        external_id,
    )
    if row is None:
        raise ValueError(f"unknown user {external_id!r} for this scope")
    return dict(row)


async def list_end_users(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT {_END_USER_COLS}, "
        "       (SELECT count(*) FROM sessions s "
        "        WHERE s.end_user_id = eu.id AND s.deleted_at IS NULL) AS session_count, "
        "       (SELECT max(s.started_at) FROM sessions s "
        "        WHERE s.end_user_id = eu.id AND s.deleted_at IS NULL) AS last_session_at "
        "FROM end_users eu WHERE eu.workspace_id = $1 ORDER BY eu.created_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def end_users_with_activity_since(workspace_id: UUID, since) -> list[dict]:
    """The users a curator run can actually write for: those with events after
    the watermark.

    The prompt names every user it lists, so listing all of them makes the
    prompt grow with the size of the customer base rather than with the work in
    front of it. A user who said nothing since the last run cannot have
    anything curated for them, so naming them costs tokens and buys nothing —
    and at a few thousand users it stops the run working at all.
    """
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT {_END_USER_COLS} FROM end_users eu "
        "WHERE eu.workspace_id = $1 AND (EXISTS ("
        "  SELECT 1 FROM sessions s "
        "  JOIN history_events he ON he.owner_user_id = s.owner_user_id "
        "    AND he.session_id = s.session_id "
        "  WHERE s.end_user_id = eu.id AND s.deleted_at IS NULL "
        "    AND ($2::timestamptz IS NULL OR he.created_at > $2)"
        # A file upload is work for its user too — a user whose only delta is
        # files would otherwise never be named in the prompt.
        ") OR EXISTS ("
        "  SELECT 1 FROM files f WHERE f.end_user_id = eu.id "
        "    AND f.deleted_at IS NULL "
        "    AND ($2::timestamptz IS NULL OR f.created_at > $2)"
        ")) ORDER BY eu.created_at",
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

    end_users = await end_users_with_activity_since(workspace["id"], since)
    return prompts.render_external_curator_prompt(
        str(workspace["external_wiki_folder_id"]),
        [
            {
                "name": end_user["name"],
                "notepad_folder_id": str(end_user["notepad_folder_id"]),
                "share_wiki": end_user["share_wiki"],
            }
            for end_user in end_users
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
        "SELECT count(*) FROM sessions s JOIN end_users eu ON eu.id = s.end_user_id "
        "WHERE eu.workspace_id = $1 AND s.deleted_at IS NULL",
        workspace["id"],
    )
    return {"wiki_page_count": wiki_page_count, "user_session_count": session_count}


async def workspace_sessions(workspace: dict, limit: int = 200) -> list[dict]:
    """Every session in the workspace, newest first, labelled by user.

    Sessions with no user are the workspace's own agents — most usefully the
    curator's runs, which the console shows in the same list so the developer
    can see when their users' sessions were read."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT s.session_id, s.agent_name, s.started_at, s.title, "
        "       eu.id AS user_id, eu.name AS user_name, eu.external_id AS user_external_id, "
        "       COUNT(he.id)::int AS event_count, "
        "       COALESCE(MAX(he.created_at), s.started_at) AS last_event_at "
        "FROM sessions s "
        "LEFT JOIN end_users eu ON eu.id = s.end_user_id "
        "LEFT JOIN history_events he "
        "  ON he.owner_user_id = s.owner_user_id AND he.session_id = s.session_id "
        "WHERE s.owner_user_id = $1 AND s.deleted_at IS NULL "
        "GROUP BY s.session_id, s.agent_name, s.started_at, s.title, eu.id, eu.name, eu.external_id "
        "ORDER BY last_event_at DESC LIMIT $2",
        workspace["scope_user_id"],
        limit,
    )
    return [dict(r) for r in rows]


async def workspace_files(workspace: dict) -> dict:
    """The console's files view: the shared wiki's pages and files, and each
    user's own material (notepad pages plus uploaded files)."""
    pool = get_pool()
    wiki_ids = list(
        await files_tree_service.folder_subtree_ids(workspace["external_wiki_folder_id"])
    )
    wiki_pages = await pool.fetch(
        "SELECT id, name, updated_at FROM pages "
        "WHERE folder_id = ANY($1) AND deleted_at IS NULL ORDER BY updated_at DESC",
        wiki_ids,
    )
    wiki_files = await pool.fetch(
        "SELECT id, name, size_bytes, created_at FROM files "
        "WHERE folder_id = ANY($1) AND deleted_at IS NULL ORDER BY created_at DESC",
        wiki_ids,
    )
    users = []
    for end_user in await list_end_users(workspace["id"]):
        notepad_ids = list(
            await files_tree_service.folder_subtree_ids(end_user["notepad_folder_id"])
        )
        notepad_pages = await pool.fetch(
            "SELECT id, name, updated_at FROM pages "
            "WHERE folder_id = ANY($1) AND deleted_at IS NULL ORDER BY updated_at DESC",
            notepad_ids,
        )
        files = await pool.fetch(
            "SELECT id, name, size_bytes, created_at FROM files "
            "WHERE end_user_id = $1 AND deleted_at IS NULL ORDER BY created_at DESC",
            end_user["id"],
        )
        users.append(
            {
                "id": str(end_user["id"]),
                "name": end_user["name"],
                "external_id": end_user["external_id"],
                "notepad_folder_id": str(end_user["notepad_folder_id"]),
                "notepad_pages": [dict(r) for r in notepad_pages],
                "files": [dict(r) for r in files],
            }
        )
    return {
        "wiki_folder_id": str(workspace["external_wiki_folder_id"]),
        "wiki_pages": [dict(r) for r in wiki_pages],
        "wiki_files": [dict(r) for r in wiki_files],
        "users": users,
    }


async def get_end_user(end_user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_END_USER_COLS} FROM end_users eu WHERE eu.id = $1", end_user_id
    )
    return dict(row) if row else None


async def update_end_user(
    end_user_id: UUID, name: str | None = None, share_wiki: bool | None = None
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        f"UPDATE end_users SET "
        "  name = COALESCE($2, name), "
        "  share_wiki = COALESCE($3, share_wiki) "
        f"WHERE id = $1 RETURNING {_END_USER_COLS_PLAIN}",
        end_user_id,
        name,
        share_wiki,
    )
    if row is None:
        raise ValueError("user not found")
    return dict(row)


async def end_user_detail(end_user: dict) -> dict:
    """Everything the console shows about one user: their transcripts, the
    files their uploads carried, and the notepad the curator writes for them."""
    pool = get_pool()
    sessions = await pool.fetch(
        "SELECT s.session_id, s.agent_name, s.started_at, s.title, "
        "       COUNT(he.id)::int AS event_count, "
        "       COALESCE(MAX(he.created_at), s.started_at) AS last_event_at "
        "FROM sessions s "
        "LEFT JOIN history_events he "
        "  ON he.owner_user_id = s.owner_user_id AND he.session_id = s.session_id "
        "WHERE s.end_user_id = $1 AND s.deleted_at IS NULL "
        "GROUP BY s.session_id, s.agent_name, s.started_at, s.title "
        "ORDER BY last_event_at DESC",
        end_user["id"],
    )
    files = await pool.fetch(
        "SELECT id, name, content_type, size_bytes, created_at "
        "FROM files WHERE end_user_id = $1 AND deleted_at IS NULL "
        "ORDER BY created_at DESC",
        end_user["id"],
    )
    notepad_pages = await pool.fetch(
        "SELECT id, name, updated_at FROM pages "
        "WHERE folder_id = ANY($1) AND deleted_at IS NULL ORDER BY updated_at DESC",
        list(await files_tree_service.folder_subtree_ids(end_user["notepad_folder_id"])),
    )
    workspace = await workspace_service.get_workspace(end_user["workspace_id"])
    sources = await source_service.list_connected_sources(
        workspace["scope_user_id"], end_user_id=end_user["id"]
    )
    return {
        "user": end_user,
        "sessions": [dict(r) for r in sessions],
        "files": [dict(r) for r in files],
        "notepad_pages": [dict(r) for r in notepad_pages],
        "sources": sources,
    }
