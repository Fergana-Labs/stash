"""Workspace service: CRUD, membership, invite codes."""

import secrets
from uuid import UUID

from ..database import get_pool


async def create_workspace(
    name: str,
    description: str,
    creator_id: UUID,
    is_public: bool = False,
) -> dict:
    """Create a workspace with the creator as owner."""
    pool = get_pool()
    invite_code = ""
    for _ in range(5):
        invite_code = secrets.token_urlsafe(6)[:8]
        exists = await pool.fetchval(
            "SELECT 1 FROM workspaces WHERE invite_code = $1",
            invite_code,
        )
        if not exists:
            break

    row = await pool.fetchrow(
        "INSERT INTO workspaces (name, description, creator_id, invite_code) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, name, description, creator_id, invite_code, "
        "created_at, updated_at, summary, tags, category, discoverable, featured, "
        "cover_image_url, home_background, fork_count, forked_from_workspace_id",
        name,
        description,
        creator_id,
        invite_code,
    )
    ws = dict(row)
    ws["is_public"] = is_public
    # Auto-add creator as owner
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
        ws["id"],
        creator_id,
    )
    if is_public:
        from . import permission_service

        await permission_service.set_visibility("workspace", ws["id"], "public")
    ws["member_count"] = 1
    return ws


async def get_workspace(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT w.id, w.name, w.description, w.creator_id, w.invite_code, "
        "COALESCE("
        "  (SELECT visibility = 'public' FROM object_permissions "
        "   WHERE object_type = 'workspace' AND object_id = w.id), "
        "  false"
        ") AS is_public, "
        "w.created_at, w.updated_at, w.summary, w.tags, w.category, "
        "w.discoverable, w.featured, "
        "w.cover_image_url, w.home_background, w.fork_count, w.forked_from_workspace_id, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w WHERE w.id = $1",
        workspace_id,
    )
    return dict(row) if row else None


async def list_public_workspaces() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT w.id, w.name, w.description, w.creator_id, w.invite_code, "
        "true AS is_public, "
        "w.created_at, w.updated_at, w.summary, w.tags, w.category, "
        "w.discoverable, w.featured, "
        "w.cover_image_url, w.home_background, w.fork_count, w.forked_from_workspace_id, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w "
        "WHERE EXISTS ("
        "  SELECT 1 FROM object_permissions op "
        "  WHERE op.object_type = 'workspace' AND op.object_id = w.id "
        "    AND op.visibility = 'public'"
        ") "
        "ORDER BY w.created_at DESC",
    )
    return [dict(r) for r in rows]


async def list_user_workspaces(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT w.id, w.name, w.description, w.creator_id, w.invite_code, "
        "COALESCE("
        "  (SELECT visibility = 'public' FROM object_permissions "
        "   WHERE object_type = 'workspace' AND object_id = w.id), "
        "  false"
        ") AS is_public, "
        "w.created_at, w.updated_at, w.summary, w.tags, w.category, "
        "w.discoverable, w.featured, "
        "w.cover_image_url, w.home_background, w.fork_count, w.forked_from_workspace_id, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w "
        "JOIN workspace_members wm ON wm.workspace_id = w.id "
        "WHERE wm.user_id = $1 ORDER BY w.created_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def update_workspace(
    workspace_id: UUID,
    name: str | None = None,
    description: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
    cover_image_url: str | None = None,
    home_background: dict | None = None,
    is_public: bool | None = None,
) -> dict | None:
    """Update a workspace. `is_public` writes into `object_permissions`
    (the column on workspaces is gone — visibility lives in one place)."""
    pool = get_pool()
    sets, args, idx = [], [], 1
    for col, val in (
        ("name", name),
        ("description", description),
        ("summary", summary),
        ("tags", tags),
        ("category", category),
        ("cover_image_url", cover_image_url),
        ("home_background", home_background),
    ):
        if val is not None:
            sets.append(f"{col} = ${idx}")
            args.append(val)
            idx += 1
    if is_public is not None:
        from . import permission_service

        await permission_service.set_visibility(
            "workspace", workspace_id, "public" if is_public else "inherit"
        )
    if not sets:
        return await get_workspace(workspace_id)
    sets.append("updated_at = now()")
    args.append(workspace_id)
    await pool.execute(
        f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ${idx}",
        *args,
    )
    return await get_workspace(workspace_id)


async def delete_workspace(workspace_id: UUID, user_id: UUID) -> bool:
    """Delete workspace. Only owner can delete."""
    pool = get_pool()
    role = await get_member_role(workspace_id, user_id)
    if role != "owner":
        return False
    result = await pool.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)
    return result == "DELETE 1"


async def join_workspace(workspace_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    exists = await pool.fetchval(
        "SELECT 1 FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    if exists:
        return await get_workspace(workspace_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        workspace_id,
        user_id,
    )
    return await get_workspace(workspace_id)


async def rotate_invite_code(workspace_id: UUID, user_id: UUID) -> dict | None:
    """Generate a new invite_code, invalidating the previous one. Owner only."""
    role = await get_member_role(workspace_id, user_id)
    if role != "owner":
        return None
    pool = get_pool()
    new_code = ""
    for _ in range(5):
        new_code = secrets.token_urlsafe(6)[:8]
        exists = await pool.fetchval(
            "SELECT 1 FROM workspaces WHERE invite_code = $1",
            new_code,
        )
        if not exists:
            break
    await pool.execute(
        "UPDATE workspaces SET invite_code = $1, updated_at = now() WHERE id = $2",
        new_code,
        workspace_id,
    )
    return await get_workspace(workspace_id)


async def join_by_invite(invite_code: str, user_id: UUID) -> dict | None:
    pool = get_pool()
    ws = await pool.fetchrow(
        "SELECT id FROM workspaces WHERE invite_code = $1",
        invite_code,
    )
    if not ws:
        return None
    return await join_workspace(ws["id"], user_id)


async def leave_workspace(workspace_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2 AND role != 'owner'",
        workspace_id,
        user_id,
    )
    if result == "DELETE 1":
        await pool.execute(
            "DELETE FROM webhooks WHERE workspace_id = $1 AND user_id = $2",
            workspace_id,
            user_id,
        )
        return True
    return False


async def get_members(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT u.id AS user_id, u.name, u.display_name, wm.role, wm.joined_at "
        "FROM workspace_members wm JOIN users u ON u.id = wm.user_id "
        "WHERE wm.workspace_id = $1 ORDER BY wm.joined_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def get_member_role(workspace_id: UUID, user_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT role FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    return row["role"] if row else None


async def is_member(workspace_id: UUID, user_id: UUID) -> bool:
    return await get_member_role(workspace_id, user_id) is not None


async def fork_workspace(
    source_id: UUID,
    forker_id: UUID,
    name: str | None = None,
) -> dict | None:
    """Fork a public workspace into a new private workspace owned by forker.

    Clones folders (preserving nesting), pages, page_links, tables (schema +
    rows), and history_events. Skips files, session_transcripts, members,
    webhooks, and invite tokens.
    """
    pool = get_pool()
    source = await pool.fetchrow(
        "SELECT w.id, w.name, w.description, w.summary, w.home_background, "
        "EXISTS("
        "  SELECT 1 FROM object_permissions op "
        "  WHERE op.object_type = 'workspace' AND op.object_id = w.id AND op.visibility = 'public'"
        ") AS is_public "
        "FROM workspaces w WHERE w.id = $1",
        source_id,
    )
    if not source or not source["is_public"]:
        return None

    new_name = name or f"{source['name']} (fork)"
    invite_code = ""
    for _ in range(5):
        invite_code = secrets.token_urlsafe(6)[:8]
        if not await pool.fetchval("SELECT 1 FROM workspaces WHERE invite_code = $1", invite_code):
            break

    async with pool.acquire() as conn:
        async with conn.transaction():
            new_ws_row = await conn.fetchrow(
                "INSERT INTO workspaces (name, description, summary, home_background, creator_id, "
                "invite_code, forked_from_workspace_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "RETURNING id, name, description, creator_id, invite_code, "
                "created_at, updated_at, summary, tags, category, discoverable, featured, "
                "cover_image_url, home_background, fork_count, forked_from_workspace_id",
                new_name,
                source["description"] or "",
                source["summary"],
                source["home_background"],
                forker_id,
                invite_code,
                source_id,
            )
            new_ws_id = new_ws_row["id"]

            await conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES ($1, $2, 'owner')",
                new_ws_id,
                forker_id,
            )

            # Folders first (BFS by parent_folder_id so each insert sees its
            # parent already in the map), then pages, then page_links.
            folders = await conn.fetch(
                "SELECT id, parent_folder_id, name FROM folders WHERE workspace_id = $1",
                source_id,
            )
            folder_id_map: dict = {}
            remaining = list(folders)
            while remaining:
                progressed = False
                next_round = []
                for f in remaining:
                    if f["parent_folder_id"] is None:
                        new_parent = None
                    elif f["parent_folder_id"] in folder_id_map:
                        new_parent = folder_id_map[f["parent_folder_id"]]
                    else:
                        next_round.append(f)
                        continue
                    new_id = await conn.fetchval(
                        "INSERT INTO folders (workspace_id, parent_folder_id, name, created_by) "
                        "VALUES ($1, $2, $3, $4) RETURNING id",
                        new_ws_id,
                        new_parent,
                        f["name"],
                        forker_id,
                    )
                    folder_id_map[f["id"]] = new_id
                    progressed = True
                if not progressed:
                    # Orphan rows (parent_folder_id pointing nowhere); reparent
                    # them to the workspace root rather than dropping them.
                    for f in next_round:
                        new_id = await conn.fetchval(
                            "INSERT INTO folders (workspace_id, parent_folder_id, name, created_by) "
                            "VALUES ($1, NULL, $2, $3) RETURNING id",
                            new_ws_id,
                            f["name"],
                            forker_id,
                        )
                        folder_id_map[f["id"]] = new_id
                    break
                remaining = next_round

            page_id_map: dict = {}
            pages = await conn.fetch(
                "SELECT id, folder_id, name, content_markdown, content_html, "
                "content_type, content_hash, metadata "
                "FROM pages WHERE workspace_id = $1",
                source_id,
            )
            for p in pages:
                new_page_id = await conn.fetchval(
                    "INSERT INTO pages "
                    "(workspace_id, folder_id, name, content_markdown, content_html, "
                    "content_type, content_hash, metadata, created_by) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
                    new_ws_id,
                    folder_id_map.get(p["folder_id"]) if p["folder_id"] else None,
                    p["name"],
                    p["content_markdown"] or "",
                    p["content_html"] or "",
                    p["content_type"],
                    p["content_hash"],
                    p["metadata"] or {},
                    forker_id,
                )
                page_id_map[p["id"]] = new_page_id

            # Page links — only re-create links where both endpoints were cloned.
            if page_id_map:
                links = await conn.fetch(
                    "SELECT source_page_id, target_page_id, link_text FROM page_links "
                    "WHERE source_page_id = ANY($1::uuid[])",
                    list(page_id_map.keys()),
                )
                for ln in links:
                    new_src = page_id_map.get(ln["source_page_id"])
                    new_tgt = page_id_map.get(ln["target_page_id"])
                    if new_src and new_tgt:
                        await conn.execute(
                            "INSERT INTO page_links (source_page_id, target_page_id, link_text) "
                            "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                            new_src,
                            new_tgt,
                            ln["link_text"],
                        )

            # Tables: clone schema (no embedding_config — re-enable in fork manually),
            # then bulk-insert rows preserving order. Embeddings are not copied.
            tables = await conn.fetch(
                "SELECT id, name, description, columns, views FROM tables "
                "WHERE workspace_id = $1",
                source_id,
            )
            for t in tables:
                new_table_id = await conn.fetchval(
                    "INSERT INTO tables (workspace_id, name, description, columns, views, created_by) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                    new_ws_id,
                    t["name"],
                    t["description"] or "",
                    t["columns"],
                    t["views"],
                    forker_id,
                )
                rows = await conn.fetch(
                    "SELECT data, row_order FROM table_rows WHERE table_id = $1 "
                    "ORDER BY row_order, created_at",
                    t["id"],
                )
                for r in rows:
                    await conn.execute(
                        "INSERT INTO table_rows (table_id, data, row_order, created_by) "
                        "VALUES ($1, $2, $3, $4)",
                        new_table_id,
                        r["data"],
                        r["row_order"],
                        forker_id,
                    )

            # History events: preserve original author, agent_name, content,
            # event_type, session_id, tool_name, metadata, attachments, created_at.
            # Embeddings are not copied.
            await conn.execute(
                "INSERT INTO history_events (workspace_id, created_by, agent_name, "
                "event_type, session_id, tool_name, content, metadata, attachments, "
                "created_at) "
                "SELECT $1, created_by, agent_name, event_type, session_id, tool_name, "
                "content, metadata, attachments, created_at "
                "FROM history_events WHERE workspace_id = $2",
                new_ws_id,
                source_id,
            )

            await conn.execute(
                "UPDATE workspaces SET fork_count = fork_count + 1 WHERE id = $1",
                source_id,
            )

    new_ws = dict(new_ws_row)
    new_ws["is_public"] = False
    new_ws["member_count"] = 1
    return new_ws


async def kick_member(workspace_id: UUID, target_user_id: UUID, kicker_id: UUID) -> bool:
    """Only owners can kick. Owners can't be kicked."""
    pool = get_pool()
    kicker_role = await get_member_role(workspace_id, kicker_id)
    target_role = await get_member_role(workspace_id, target_user_id)
    if not kicker_role or not target_role:
        return False
    if target_role == "owner":
        return False
    if kicker_role != "owner":
        return False
    result = await pool.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        target_user_id,
    )
    if result == "DELETE 1":
        await pool.execute(
            "DELETE FROM webhooks WHERE workspace_id = $1 AND user_id = $2",
            workspace_id,
            target_user_id,
        )
        return True
    return False


# Role-based authorization helpers (PR 7).
ROLES_CAN_READ = {"owner", "editor", "viewer"}
ROLES_CAN_WRITE = {"owner", "editor"}
ROLES_ADMIN = {"owner"}


async def can_read(workspace_id: UUID, user_id: UUID) -> bool:
    role = await get_member_role(workspace_id, user_id)
    return role in ROLES_CAN_READ


async def can_write(workspace_id: UUID, user_id: UUID) -> bool:
    role = await get_member_role(workspace_id, user_id)
    return role in ROLES_CAN_WRITE


async def is_owner(workspace_id: UUID, user_id: UUID) -> bool:
    role = await get_member_role(workspace_id, user_id)
    return role in ROLES_ADMIN


async def set_member_role(
    workspace_id: UUID,
    target_user_id: UUID,
    setter_id: UUID,
    role: str,
) -> bool:
    """Only owners can change roles. Owners cannot demote themselves
    (would lock the workspace if they're the only owner). Role must be
    one of owner/editor/viewer."""
    if role not in ("owner", "editor", "viewer"):
        return False
    if not await is_owner(workspace_id, setter_id):
        return False
    pool = get_pool()
    target_role = await get_member_role(workspace_id, target_user_id)
    if target_role is None:
        return False
    if target_role == "owner" and role != "owner":
        # Prevent demoting the last owner.
        owner_count = await pool.fetchval(
            "SELECT COUNT(*) FROM workspace_members " "WHERE workspace_id = $1 AND role = 'owner'",
            workspace_id,
        )
        if owner_count <= 1:
            return False
    await pool.execute(
        "UPDATE workspace_members SET role = $1 " "WHERE workspace_id = $2 AND user_id = $3",
        role,
        workspace_id,
        target_user_id,
    )
    return True
