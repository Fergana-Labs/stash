"""Curated Views — published subsets of a workspace's resources."""

from __future__ import annotations

import re
import secrets
from uuid import UUID

from ..database import get_pool
from . import workspace_service

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    base = _SLUG_RE.sub("-", title.lower()).strip("-")[:64] or "view"
    return f"{base}-{secrets.token_urlsafe(4)[:6].lower()}"


# `is_public` is no longer a column on `views` — it's derived from
# object_permissions (visibility='public' on object_type='view').
_VIEW_SELECT = (
    "SELECT v.id, v.workspace_id, v.slug, v.title, v.description, v.owner_id, "
    "COALESCE("
    "  (SELECT visibility = 'public' FROM object_permissions "
    "   WHERE object_type = 'view' AND object_id = v.id), "
    "  false"
    ") AS is_public, "
    "v.cover_image_url, v.view_count, v.created_at, v.updated_at FROM views v"
)
_VIEW_COLS = (
    "v.id, v.workspace_id, v.slug, v.title, v.description, v.owner_id, "
    "COALESCE("
    "  (SELECT visibility = 'public' FROM object_permissions "
    "   WHERE object_type = 'view' AND object_id = v.id), "
    "  false"
    ") AS is_public, "
    "v.cover_image_url, v.view_count, v.created_at, v.updated_at"
)


async def _attach_items(view: dict) -> dict:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT object_type, object_id, position, label_override "
        "FROM view_items WHERE view_id = $1 ORDER BY position, object_type, object_id",
        view["id"],
    )
    view["items"] = [dict(r) for r in rows]
    return view


async def _replace_items(conn, view_id: UUID, items: list) -> None:
    await conn.execute("DELETE FROM view_items WHERE view_id = $1", view_id)
    for i, item in enumerate(items):
        await conn.execute(
            "INSERT INTO view_items (view_id, object_type, object_id, position, label_override) "
            "VALUES ($1, $2, $3, $4, $5)",
            view_id,
            item.object_type,
            item.object_id,
            item.position if item.position is not None else i,
            item.label_override,
        )


async def create_view(
    workspace_id: UUID,
    owner_id: UUID,
    title: str,
    description: str,
    is_public: bool,
    cover_image_url: str | None,
    items: list,
) -> dict:
    pool = get_pool()
    slug = _slugify(title)
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "INSERT INTO views (workspace_id, slug, title, description, owner_id, "
                "cover_image_url) VALUES ($1, $2, $3, $4, $5, $6) "
                "RETURNING id, workspace_id, slug, title, description, owner_id, "
                "cover_image_url, view_count, created_at, updated_at",
                workspace_id,
                slug,
                title,
                description,
                owner_id,
                cover_image_url,
            )
            await _replace_items(conn, row["id"], items)
    if is_public:
        from . import permission_service

        await permission_service.set_visibility("view", row["id"], "public")
    out = dict(row)
    out["is_public"] = bool(is_public)
    return await _attach_items(out)


async def _object_title(object_type: str, object_id: UUID) -> str:
    """Best-effort human label for an underlying object — used as the default
    View title when minting a share-link View."""
    pool = get_pool()
    if object_type == "folder":
        row = await pool.fetchrow("SELECT name FROM folders WHERE id = $1", object_id)
    elif object_type == "page":
        row = await pool.fetchrow("SELECT name FROM pages WHERE id = $1", object_id)
    elif object_type == "table":
        row = await pool.fetchrow("SELECT name FROM tables WHERE id = $1", object_id)
    elif object_type == "file":
        row = await pool.fetchrow("SELECT name FROM files WHERE id = $1", object_id)
    elif object_type == "history":
        row = await pool.fetchrow(
            "SELECT agent_name AS name FROM history_events WHERE id = $1", object_id
        )
    else:
        row = None
    return row["name"] if row else "Shared item"


async def find_or_create_share_link_view(
    workspace_id: UUID,
    owner_id: UUID,
    object_type: str,
    object_id: UUID,
) -> dict:
    """Reuse-or-create the one-item View that backs the Copy Link button.

    Idempotent on (owner, object_type, object_id): clicking Copy Link a second
    time on the same object returns the same /v/{slug} URL."""
    pool = get_pool()
    existing = await pool.fetchrow(
        f"SELECT {_VIEW_COLS} FROM views v "
        "WHERE v.owner_id = $1 "
        "AND (SELECT COUNT(*) FROM view_items WHERE view_id = v.id) = 1 "
        "AND EXISTS (SELECT 1 FROM view_items "
        "            WHERE view_id = v.id AND object_type = $2 AND object_id = $3) "
        "ORDER BY v.created_at LIMIT 1",
        owner_id,
        object_type,
        object_id,
    )
    if existing:
        return await _attach_items(dict(existing))

    title = await _object_title(object_type, object_id)
    slug = _slugify(title)
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "INSERT INTO views (workspace_id, slug, title, description, owner_id, "
                "cover_image_url) VALUES ($1, $2, $3, $4, $5, NULL) "
                "RETURNING id, workspace_id, slug, title, description, owner_id, "
                "cover_image_url, view_count, created_at, updated_at",
                workspace_id,
                slug,
                title,
                "",
                owner_id,
            )
            await conn.execute(
                "INSERT INTO view_items (view_id, object_type, object_id, position, label_override) "
                "VALUES ($1, $2, $3, 0, NULL)",
                row["id"],
                object_type,
                object_id,
            )
    from . import permission_service

    await permission_service.set_visibility("view", row["id"], "public")
    out = dict(row)
    out["is_public"] = True
    return await _attach_items(out)


async def update_view(
    view_id: UUID,
    user_id: UUID,
    *,
    title: str | None = None,
    description: str | None = None,
    is_public: bool | None = None,
    cover_image_url: str | None = None,
    items: list | None = None,
) -> dict | None:
    pool = get_pool()
    view = await pool.fetchrow(
        "SELECT id, workspace_id, owner_id FROM views WHERE id = $1", view_id
    )
    if not view or view["owner_id"] != user_id:
        return None

    sets, args, idx = [], [], 1
    for col, val in (
        ("title", title),
        ("description", description),
        ("cover_image_url", cover_image_url),
    ):
        if val is not None:
            sets.append(f"{col} = ${idx}")
            args.append(val)
            idx += 1

    async with pool.acquire() as conn:
        async with conn.transaction():
            if sets:
                sets.append("updated_at = now()")
                args.append(view_id)
                await conn.execute(
                    f"UPDATE views SET {', '.join(sets)} WHERE id = ${idx}",
                    *args,
                )
            if items is not None:
                await _replace_items(conn, view_id, items)

    if is_public is not None:
        from . import permission_service

        await permission_service.set_visibility(
            "view", view_id, "public" if is_public else "inherit"
        )

    row = await pool.fetchrow(f"{_VIEW_SELECT} WHERE v.id = $1", view_id)
    return await _attach_items(dict(row))


async def delete_view(view_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM views WHERE id = $1 AND owner_id = $2", view_id, user_id
    )
    return result == "DELETE 1"


async def list_public_views(
    *,
    query: str | None = None,
    sort: str = "trending",
    limit: int = 48,
) -> list[dict]:
    """Catalog of Views whose every underlying item is anonymously readable."""
    from . import permission_service

    pool = get_pool()
    where = ["1=1"]
    args: list = []
    idx = 1
    if query:
        where.append(f"(v.title ILIKE ${idx} OR v.description ILIKE ${idx})")
        args.append(f"%{query}%")
        idx += 1

    if sort == "newest":
        order = "v.created_at DESC, v.id DESC"
    elif sort == "popular":
        order = "v.view_count DESC, v.updated_at DESC, v.id DESC"
    else:
        order = "v.updated_at DESC, v.id DESC"

    rows = await pool.fetch(
        f"SELECT v.id, v.workspace_id, v.slug, v.title, v.description, v.owner_id, "
        f"v.cover_image_url, v.view_count, v.created_at, v.updated_at, "
        f"u.name AS owner_name, u.display_name AS owner_display_name, "
        f"w.name AS workspace_name "
        f"FROM views v JOIN users u ON u.id = v.owner_id "
        f"JOIN workspaces w ON w.id = v.workspace_id "
        f"WHERE {' AND '.join(where)} ORDER BY {order} LIMIT {int(limit) * 2}",
        *args,
    )

    out: list[dict] = []
    for r in rows:
        view = await _attach_items(dict(r))
        readable = True
        for item in view["items"]:
            ok = await permission_service.check_access(
                item["object_type"], item["object_id"], None, workspace_id=view["workspace_id"]
            )
            if not ok:
                readable = False
                break
        if readable:
            out.append(
                {
                    "id": str(view["id"]),
                    "slug": view["slug"],
                    "title": view["title"],
                    "description": view["description"],
                    "cover_image_url": view["cover_image_url"],
                    "view_count": view["view_count"],
                    "owner_name": view.get("owner_name"),
                    "owner_display_name": view.get("owner_display_name"),
                    "workspace_id": str(view["workspace_id"]),
                    "workspace_name": view.get("workspace_name"),
                    "item_count": len(view["items"]),
                    "created_at": view["created_at"].isoformat(),
                    "updated_at": view["updated_at"].isoformat(),
                }
            )
            if len(out) >= limit:
                break
    return out


async def list_workspace_views(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        f"{_VIEW_SELECT} WHERE v.workspace_id = $1 ORDER BY updated_at DESC",
        workspace_id,
    )
    return [await _attach_items(dict(r)) for r in rows]


async def get_view(view_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"{_VIEW_SELECT} WHERE v.id = $1", view_id)
    return await _attach_items(dict(row)) if row else None


async def get_public_view(slug: str, viewer_id: UUID | None = None) -> dict | None:
    """Resolve a View by slug for the given viewer (None = anonymous).

    Strict access: the View renders iff the viewer can read every one of its
    items via the object-level permission service. There's no separate View
    ACL — we derive it from the items, which avoids the orphan-View bug
    (a public View over a now-private item would silently leak today).
    """
    from . import permission_service

    pool = get_pool()
    row = await pool.fetchrow(f"{_VIEW_SELECT} WHERE v.slug = $1", slug)
    if not row:
        return None
    view = await _attach_items(dict(row))

    # Strict mode: the View renders iff every underlying item is readable to
    # the viewer. There's no separate View ACL — Views are pure presentation,
    # so an item being privately overridden hides the whole publication, even
    # for the workspace owner browsing the public URL. Owners can always
    # navigate via the workspace UI.
    for item in view["items"]:
        ok = await permission_service.check_access(
            item["object_type"], item["object_id"], viewer_id, workspace_id=view["workspace_id"]
        )
        if not ok:
            return None

    await pool.execute("UPDATE views SET view_count = view_count + 1 WHERE id = $1", view["id"])

    ws = await pool.fetchrow(
        "SELECT w.name, "
        "EXISTS("
        "  SELECT 1 FROM object_permissions op "
        "  WHERE op.object_type = 'workspace' AND op.object_id = w.id AND op.visibility = 'public'"
        ") AS is_public "
        "FROM workspaces w WHERE w.id = $1",
        view["workspace_id"],
    )
    view["_workspace_name"] = ws["name"] if ws else ""
    view["_workspace_is_public"] = bool(ws and ws["is_public"])
    return view


async def inline_items(view: dict, viewer_id: UUID | None = None) -> list[dict]:
    """Resolve each view_item into a dict with {object_type, object_id, position,
    label, inline} where inline is a type-specific payload."""
    from . import permission_service

    pool = get_pool()
    out: list[dict] = []
    for item in view["items"]:
        obj_type = item["object_type"]
        obj_id = item["object_id"]
        label = item.get("label_override") or ""
        inline: dict = {}
        if obj_type == "folder":
            folder = await pool.fetchrow("SELECT name FROM folders WHERE id = $1", obj_id)
            if folder:
                label = label or folder["name"]
                # Recursive: include every page in this folder and its
                # descendants so a shared folder behaves like the old
                # "shared notebook" did.
                pages = await pool.fetch(
                    "WITH RECURSIVE subtree AS ("
                    "  SELECT id FROM folders WHERE id = $1"
                    "  UNION ALL"
                    "  SELECT f.id FROM folders f JOIN subtree s ON f.parent_folder_id = s.id"
                    ") "
                    "SELECT p.id, p.name, p.content_markdown, p.content_html, p.content_type, "
                    "p.html_layout, p.updated_at FROM pages p "
                    "WHERE p.folder_id IN (SELECT id FROM subtree) "
                    "ORDER BY p.created_at, p.name",
                    obj_id,
                )
                visible_pages = []
                for p in pages:
                    if await permission_service.check_access(
                        "page", p["id"], viewer_id, workspace_id=view["workspace_id"]
                    ):
                        visible_pages.append(p)
                inline = {
                    "pages": [
                        {
                            "id": str(p["id"]),
                            "name": p["name"],
                            "content_type": p["content_type"],
                            "content_markdown": p["content_markdown"],
                            "content_html": p["content_html"],
                            "html_layout": p["html_layout"],
                            "updated_at": p["updated_at"].isoformat(),
                        }
                        for p in visible_pages
                    ],
                }
        elif obj_type == "page":
            p = await pool.fetchrow(
                "SELECT id, name, content_markdown, content_html, content_type, "
                "html_layout, updated_at FROM pages WHERE id = $1",
                obj_id,
            )
            if p:
                label = label or p["name"]
                inline = {
                    "page": {
                        "id": str(p["id"]),
                        "name": p["name"],
                        "content_type": p["content_type"],
                        "content_markdown": p["content_markdown"],
                        "content_html": p["content_html"],
                        "html_layout": p["html_layout"],
                        "updated_at": p["updated_at"].isoformat(),
                    }
                }
        elif obj_type == "table":
            t = await pool.fetchrow(
                "SELECT name, description, columns FROM tables WHERE id = $1", obj_id
            )
            if t:
                label = label or t["name"]
                rows = await pool.fetch(
                    "SELECT data, row_order FROM table_rows WHERE table_id = $1 "
                    "ORDER BY row_order LIMIT 500",
                    obj_id,
                )
                inline = {
                    "description": t["description"],
                    "columns": t["columns"],
                    "rows": [{"data": r["data"], "row_order": r["row_order"]} for r in rows],
                }
        elif obj_type == "file":
            f = await pool.fetchrow(
                "SELECT name, content_type, size_bytes, created_at FROM files WHERE id = $1",
                obj_id,
            )
            if f:
                label = label or f["name"]
                inline = {
                    "content_type": f["content_type"],
                    "size_bytes": f["size_bytes"],
                    "created_at": f["created_at"].isoformat(),
                }
        elif obj_type == "history":
            ev = await pool.fetchrow(
                "SELECT agent_name, event_type, content, created_at "
                "FROM history_events WHERE id = $1",
                obj_id,
            )
            if ev:
                label = label or f"{ev['agent_name']} · {ev['event_type']}"
                inline = {
                    "agent_name": ev["agent_name"],
                    "event_type": ev["event_type"],
                    "content": ev["content"],
                    "created_at": ev["created_at"].isoformat(),
                }

        if not inline:
            # Object was deleted underneath the view — keep the placeholder so
            # the curator can see and prune it, but don't crash.
            label = label or "(missing)"

        out.append(
            {
                "object_type": obj_type,
                "object_id": obj_id,
                "position": item["position"],
                "label": label,
                "inline": inline,
            }
        )
    return out


def items_to_text(title: str, items: list[dict]) -> str:
    """Flatten a View's inlined items into readable markdown text."""
    parts = [f"# {title}\n"]
    for item in items:
        obj_type = item["object_type"]
        label = item.get("label", "")
        inline = item.get("inline", {})
        if not inline:
            continue

        if obj_type == "folder":
            for page in inline.get("pages", []):
                if page.get("content_markdown"):
                    parts.append(page["content_markdown"])
        elif obj_type == "page":
            page = inline.get("page", {})
            if page.get("content_markdown"):
                parts.append(page["content_markdown"])
        elif obj_type == "table":
            cols = inline.get("columns", [])
            rows = inline.get("rows", [])
            if cols:
                header = " | ".join(c["name"] for c in cols)
                sep = " | ".join("---" for _ in cols)
                table_lines = [f"## {label}", "", f"| {header} |", f"| {sep} |"]
                for r in rows[:100]:
                    vals = " | ".join(str(r["data"].get(c["name"], "")) for c in cols)
                    table_lines.append(f"| {vals} |")
                parts.append("\n".join(table_lines))
        elif obj_type == "file":
            parts.append(f"*Attached file: {label} ({inline.get('content_type', 'unknown')})*\n")
        elif obj_type == "history":
            parts.append(f"**{inline.get('agent_name', '')}** ({inline.get('event_type', '')})")
            if inline.get("content"):
                parts.append(inline["content"])
            parts.append("")

    return "\n\n".join(parts)


async def fork_view(slug: str, forker_id: UUID, name: str | None = None) -> dict | None:
    """Create a new private workspace containing only the items in the view.

    Reuses the same cloning primitives as fork_workspace but scoped to the
    view's items, not the whole source workspace.
    """
    pool = get_pool()
    view_row = await pool.fetchrow(f"{_VIEW_SELECT} WHERE slug = $1", slug)
    if not view_row:
        return None
    view = await _attach_items(dict(view_row))

    from . import permission_service

    for item in view["items"]:
        if not await permission_service.check_access(
            item["object_type"], item["object_id"], None, workspace_id=view["workspace_id"]
        ):
            return None

    source_ws = await pool.fetchrow(
        "SELECT id, name FROM workspaces WHERE id = $1", view["workspace_id"]
    )
    if not source_ws:
        return None

    new_name = name or f"{view['title']} (from {source_ws['name']})"
    invite_code = ""
    for _ in range(5):
        invite_code = secrets.token_urlsafe(6)[:8]
        if not await pool.fetchval("SELECT 1 FROM workspaces WHERE invite_code = $1", invite_code):
            break

    async with pool.acquire() as conn:
        async with conn.transaction():
            new_ws = await conn.fetchrow(
                "INSERT INTO workspaces (name, description, summary, creator_id, "
                "invite_code, forked_from_workspace_id) "
                "VALUES ($1, $2, $3, $4, $5, $6) "
                "RETURNING id, name, description, creator_id, invite_code, "
                "created_at, updated_at, summary, tags, category, featured, "
                "cover_image_url, fork_count, forked_from_workspace_id",
                new_name,
                view["description"] or "",
                view["title"],
                forker_id,
                invite_code,
                view["workspace_id"],
            )
            new_ws_id = new_ws["id"]
            await conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES ($1, $2, 'owner')",
                new_ws_id,
                forker_id,
            )

            for item in view["items"]:
                t = item["object_type"]
                src_id = item["object_id"]

                if t == "folder":
                    folder = await conn.fetchrow("SELECT name FROM folders WHERE id = $1", src_id)
                    if not folder:
                        continue
                    # Clone the folder's entire subtree (recursive folders +
                    # their pages) so the fork preserves nesting.
                    subtree = await conn.fetch(
                        "WITH RECURSIVE chain AS ("
                        "  SELECT id, parent_folder_id, name FROM folders WHERE id = $1"
                        "  UNION ALL"
                        "  SELECT f.id, f.parent_folder_id, f.name FROM folders f "
                        "  JOIN chain c ON f.parent_folder_id = c.id"
                        ") SELECT id, parent_folder_id, name FROM chain",
                        src_id,
                    )
                    folder_id_map: dict = {}
                    remaining = list(subtree)
                    while remaining:
                        progressed = False
                        next_round = []
                        for f in remaining:
                            if f["id"] == src_id:
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
                            break
                        remaining = next_round

                    pages = await conn.fetch(
                        "SELECT id, folder_id, name, content_markdown, content_html, "
                        "content_type, html_layout, content_hash, metadata FROM pages "
                        "WHERE folder_id = ANY($1::uuid[])",
                        list(folder_id_map.keys()),
                    )
                    for p in pages:
                        if not await permission_service.check_access(
                            "page", p["id"], None, workspace_id=view["workspace_id"]
                        ):
                            continue
                        await conn.execute(
                            "INSERT INTO pages "
                            "(workspace_id, folder_id, name, content_markdown, content_html, "
                            "content_type, html_layout, content_hash, metadata, created_by) "
                            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                            new_ws_id,
                            folder_id_map.get(p["folder_id"]),
                            p["name"],
                            p["content_markdown"] or "",
                            p["content_html"] or "",
                            p["content_type"],
                            p["html_layout"],
                            p["content_hash"],
                            p["metadata"] or {},
                            forker_id,
                        )

                elif t == "page":
                    src = await conn.fetchrow(
                        "SELECT name, content_markdown, content_html, content_type, "
                        "html_layout, content_hash, metadata FROM pages WHERE id = $1",
                        src_id,
                    )
                    if not src:
                        continue
                    await conn.execute(
                        "INSERT INTO pages "
                        "(workspace_id, name, content_markdown, content_html, "
                        "content_type, html_layout, content_hash, metadata, created_by) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                        new_ws_id,
                        src["name"],
                        src["content_markdown"] or "",
                        src["content_html"] or "",
                        src["content_type"],
                        src["html_layout"],
                        src["content_hash"],
                        src["metadata"] or {},
                        forker_id,
                    )

                elif t == "table":
                    src = await conn.fetchrow(
                        "SELECT name, description, columns, views FROM tables WHERE id = $1",
                        src_id,
                    )
                    if not src:
                        continue
                    new_t_id = await conn.fetchval(
                        "INSERT INTO tables (workspace_id, name, description, columns, views, created_by) "
                        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                        new_ws_id,
                        src["name"],
                        src["description"] or "",
                        src["columns"],
                        src["views"],
                        forker_id,
                    )
                    rows = await conn.fetch(
                        "SELECT data, row_order FROM table_rows WHERE table_id = $1 "
                        "ORDER BY row_order, created_at",
                        src_id,
                    )
                    for r in rows:
                        await conn.execute(
                            "INSERT INTO table_rows (table_id, data, row_order, created_by) "
                            "VALUES ($1, $2, $3, $4)",
                            new_t_id,
                            r["data"],
                            r["row_order"],
                            forker_id,
                        )

                elif t == "history":
                    src = await conn.fetchrow(
                        "SELECT created_by, agent_name, event_type, session_id, tool_name, "
                        "content, metadata, attachments, created_at "
                        "FROM history_events WHERE id = $1",
                        src_id,
                    )
                    if not src:
                        continue
                    await conn.execute(
                        "INSERT INTO history_events (workspace_id, created_by, agent_name, "
                        "event_type, session_id, tool_name, content, metadata, attachments, "
                        "created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                        new_ws_id,
                        src["created_by"],
                        src["agent_name"],
                        src["event_type"],
                        src["session_id"],
                        src["tool_name"],
                        src["content"],
                        src["metadata"],
                        src["attachments"],
                        src["created_at"],
                    )
                # files are intentionally skipped (S3 copy out of scope).

            await conn.execute(
                "UPDATE workspaces SET fork_count = fork_count + 1 WHERE id = $1",
                view["workspace_id"],
            )

    new_ws_dict = dict(new_ws)
    new_ws_dict["member_count"] = 1
    return new_ws_dict


async def user_can_manage(view_id: UUID, user_id: UUID) -> bool:
    """View management requires either being the view's owner or being an
    owner/admin of the host workspace."""
    pool = get_pool()
    row = await pool.fetchrow("SELECT workspace_id, owner_id FROM views WHERE id = $1", view_id)
    if not row:
        return False
    if row["owner_id"] == user_id:
        return True
    role = await workspace_service.get_member_role(row["workspace_id"], user_id)
    return role in ("owner", "admin")
