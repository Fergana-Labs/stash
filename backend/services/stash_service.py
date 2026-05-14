"""Product Stashes — published subsets of a workspace's resources."""

from __future__ import annotations

import re
import secrets
from uuid import UUID

from ..database import get_pool
from . import permission_service, workspace_service

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    base = _SLUG_RE.sub("-", title.lower()).strip("-")[:64] or "stash"
    return f"{base}-{secrets.token_urlsafe(4)[:6].lower()}"


_STASH_SELECT = (
    "SELECT v.id, v.workspace_id, v.slug, v.title, v.description, v.owner_id, "
    "v.is_public, "
    "v.discoverable, v.cover_image_url, v.view_count, v.created_at, v.updated_at FROM stashes v"
)
_STASH_COLS = (
    "v.id, v.workspace_id, v.slug, v.title, v.description, v.owner_id, "
    "v.is_public, "
    "v.discoverable, v.cover_image_url, v.view_count, v.created_at, v.updated_at"
)
_VISIBILITY_RANK = {"private": 0, "inherit": 0, "link": 1, "public": 2}


async def _attach_items(stash: dict) -> dict:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT object_type, object_id, position, label_override "
        "FROM stash_items WHERE stash_id = $1 ORDER BY position, object_type, object_id",
        stash["id"],
    )
    stash["items"] = [dict(r) for r in rows]
    return stash


async def _is_anonymously_readable(stash: dict) -> bool:
    for item in stash["items"]:
        ok = await permission_service.check_access(
            item["object_type"], item["object_id"], None, workspace_id=stash["workspace_id"]
        )
        if not ok:
            return False
    return True


def _mark_native(stash: dict) -> dict:
    stash["is_external"] = False
    stash["added_to_workspace_id"] = None
    return stash


def _mark_external(stash: dict, workspace_id: UUID) -> dict:
    stash["is_external"] = True
    stash["added_to_workspace_id"] = workspace_id
    return stash


async def _replace_items(conn, stash_id: UUID, items: list) -> None:
    await conn.execute("DELETE FROM stash_items WHERE stash_id = $1", stash_id)
    for i, item in enumerate(items):
        await conn.execute(
            "INSERT INTO stash_items (stash_id, object_type, object_id, position, label_override) "
            "VALUES ($1, $2, $3, $4, $5)",
            stash_id,
            item.object_type,
            item.object_id,
            item.position if item.position is not None else i,
            item.label_override,
        )


async def _make_items_public(items: list) -> None:
    for item in items:
        object_type = item.object_type if hasattr(item, "object_type") else item["object_type"]
        object_id = item.object_id if hasattr(item, "object_id") else item["object_id"]
        current = await permission_service.get_visibility(object_type, object_id)
        if _VISIBILITY_RANK.get(current, 0) < _VISIBILITY_RANK["public"]:
            await permission_service.set_visibility(object_type, object_id, "public")


async def create_stash(
    workspace_id: UUID,
    owner_id: UUID,
    title: str,
    description: str,
    is_public: bool,
    discoverable: bool,
    cover_image_url: str | None,
    items: list,
) -> dict:
    if discoverable and not is_public:
        raise ValueError("Discover Stashes must be public")
    if is_public:
        await _make_items_public(items)

    pool = get_pool()
    slug = _slugify(title)
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "INSERT INTO stashes (workspace_id, slug, title, description, owner_id, "
                "is_public, discoverable, cover_image_url) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
                "RETURNING id, workspace_id, slug, title, description, owner_id, "
                "is_public, discoverable, cover_image_url, view_count, created_at, updated_at",
                workspace_id,
                slug,
                title,
                description,
                owner_id,
                is_public,
                discoverable,
                cover_image_url,
            )
            await _replace_items(conn, row["id"], items)
    out = dict(row)
    return await _attach_items(out)


async def _object_title(object_type: str, object_id: UUID) -> str:
    """Best-effort human label for an underlying object — used as the default
    Stash title when minting a share-link Stash."""
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
    elif object_type == "session":
        row = await pool.fetchrow(
            "SELECT session_id AS name FROM sessions WHERE id = $1", object_id
        )
    else:
        row = None
    return row["name"] if row else "Shared item"


async def find_or_create_share_link_stash(
    workspace_id: UUID,
    owner_id: UUID,
    object_type: str,
    object_id: UUID,
) -> dict:
    """Reuse-or-create the one-item Stash that backs the Copy Link button.

    Idempotent on (owner, object_type, object_id): clicking Copy Link a second
    time on the same object returns the same /stashes/{slug} URL."""
    pool = get_pool()
    existing = await pool.fetchrow(
        f"SELECT {_STASH_COLS} FROM stashes v "
        "WHERE v.owner_id = $1 "
        "AND (SELECT COUNT(*) FROM stash_items WHERE stash_id = v.id) = 1 "
        "AND EXISTS (SELECT 1 FROM stash_items "
        "            WHERE stash_id = v.id AND object_type = $2 AND object_id = $3) "
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
                "INSERT INTO stashes (workspace_id, slug, title, description, owner_id, "
                "is_public, discoverable, cover_image_url) VALUES ($1, $2, $3, $4, $5, false, false, NULL) "
                "RETURNING id, workspace_id, slug, title, description, owner_id, "
                "is_public, discoverable, cover_image_url, view_count, created_at, updated_at",
                workspace_id,
                slug,
                title,
                "",
                owner_id,
            )
            await conn.execute(
                "INSERT INTO stash_items (stash_id, object_type, object_id, position, label_override) "
                "VALUES ($1, $2, $3, 0, NULL)",
                row["id"],
                object_type,
                object_id,
            )
    out = dict(row)
    return await _attach_items(out)


async def update_stash(
    stash_id: UUID,
    user_id: UUID,
    *,
    title: str | None = None,
    description: str | None = None,
    is_public: bool | None = None,
    discoverable: bool | None = None,
    cover_image_url: str | None = None,
    items: list | None = None,
) -> dict | None:
    pool = get_pool()
    stash = await pool.fetchrow(
        "SELECT id, workspace_id, owner_id, is_public FROM stashes WHERE id = $1", stash_id
    )
    if not stash or not await user_can_manage(stash_id, user_id):
        return None
    if discoverable and is_public is False:
        raise ValueError("Discover Stashes must be public")
    if discoverable:
        if not stash["is_public"] and is_public is not True:
            raise ValueError("Discover Stashes must be public")
    if is_public is False and discoverable is None:
        discoverable = False
    if is_public is True:
        publish_items = items
        if publish_items is None:
            publish_items = await pool.fetch(
                "SELECT object_type, object_id FROM stash_items WHERE stash_id = $1",
                stash_id,
            )
        await _make_items_public(publish_items)

    sets, args, idx = [], [], 1
    for col, val in (
        ("title", title),
        ("description", description),
        ("is_public", is_public),
        ("discoverable", discoverable),
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
                args.append(stash_id)
                await conn.execute(
                    f"UPDATE stashes SET {', '.join(sets)} WHERE id = ${idx}",
                    *args,
                )
            if items is not None:
                await _replace_items(conn, stash_id, items)

    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.id = $1", stash_id)
    return await _attach_items(dict(row))


async def delete_stash(stash_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    if not await user_can_manage(stash_id, user_id):
        return False
    result = await pool.execute("DELETE FROM stashes WHERE id = $1", stash_id)
    return result == "DELETE 1"


async def list_public_stashes(
    *,
    query: str | None = None,
    sort: str = "trending",
    limit: int = 48,
) -> list[dict]:
    """Catalog of Stashes whose every underlying item is anonymously readable."""
    pool = get_pool()
    where = ["v.discoverable = true"]
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
        f"v.discoverable, v.cover_image_url, v.view_count, v.created_at, v.updated_at, "
        f"u.name AS owner_name, u.display_name AS owner_display_name, "
        f"w.name AS workspace_name "
        f"FROM stashes v JOIN users u ON u.id = v.owner_id "
        f"JOIN workspaces w ON w.id = v.workspace_id "
        f"WHERE {' AND '.join(where)} ORDER BY {order} LIMIT {int(limit) * 2}",
        *args,
    )

    out: list[dict] = []
    for r in rows:
        stash = await _attach_items(dict(r))
        if await _is_anonymously_readable(stash):
            out.append(
                {
                    "id": str(stash["id"]),
                    "slug": stash["slug"],
                    "title": stash["title"],
                    "description": stash["description"],
                    "discoverable": stash["discoverable"],
                    "cover_image_url": stash["cover_image_url"],
                    "view_count": stash["view_count"],
                    "owner_name": stash.get("owner_name"),
                    "owner_display_name": stash.get("owner_display_name"),
                    "workspace_id": str(stash["workspace_id"]),
                    "workspace_name": stash.get("workspace_name"),
                    "item_count": len(stash["items"]),
                    "created_at": stash["created_at"].isoformat(),
                    "updated_at": stash["updated_at"].isoformat(),
                }
            )
            if len(out) >= limit:
                break
    return out


async def list_workspace_stashes(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    native_rows = await pool.fetch(
        f"{_STASH_SELECT} WHERE v.workspace_id = $1 ORDER BY updated_at DESC",
        workspace_id,
    )
    external_rows = await pool.fetch(
        f"SELECT {_STASH_COLS}, es.workspace_id AS added_to_workspace_id "
        "FROM external_stashes es "
        "JOIN stashes v ON v.id = es.stash_id "
        "WHERE es.workspace_id = $1 "
        "ORDER BY es.created_at DESC",
        workspace_id,
    )

    native = [_mark_native(await _attach_items(dict(row))) for row in native_rows]
    external = [
        _mark_external(await _attach_items(dict(row)), row["added_to_workspace_id"])
        for row in external_rows
    ]
    return native + external


async def add_external_stash(workspace_id: UUID, slug: str, added_by: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.slug = $1", slug)
    if not row:
        return None
    stash = await _attach_items(dict(row))
    if stash["workspace_id"] == workspace_id:
        return _mark_native(stash)
    if not await _is_anonymously_readable(stash):
        return None

    await pool.execute(
        "INSERT INTO external_stashes (workspace_id, stash_id, added_by) "
        "VALUES ($1, $2, $3) ON CONFLICT (workspace_id, stash_id) DO NOTHING",
        workspace_id,
        stash["id"],
        added_by,
    )
    return _mark_external(stash, workspace_id)


async def remove_external_stash(workspace_id: UUID, stash_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM external_stashes WHERE workspace_id = $1 AND stash_id = $2",
        workspace_id,
        stash_id,
    )
    return result == "DELETE 1"


async def list_object_stashes(workspace_id: UUID, object_type: str, object_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT {_STASH_COLS} FROM stashes v "
        "JOIN stash_items vi ON vi.stash_id = v.id "
        "WHERE v.workspace_id = $1 AND vi.object_type = $2 AND vi.object_id = $3 "
        "ORDER BY v.updated_at DESC",
        workspace_id,
        object_type,
        object_id,
    )
    return [await _attach_items(dict(row)) for row in rows]


async def get_stash(stash_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.id = $1", stash_id)
    return await _attach_items(dict(row)) if row else None


async def get_public_stash(slug: str, viewer_id: UUID | None = None) -> dict | None:
    """Resolve a Stash by slug for the given viewer (None = anonymous).

    Strict access: the Stash renders iff the viewer can read every one of its
    items via the object-level permission service. There's no separate Stash
    ACL — we derive it from the items, which avoids the orphan-Stash bug
    (a public Stash over a now-private item would silently leak today).
    """
    pool = get_pool()
    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.slug = $1", slug)
    if not row:
        return None
    stash = await _attach_items(dict(row))

    # Strict mode: the Stash renders iff every underlying item is readable to
    # the viewer. There's no separate Stash ACL — Stashes are pure presentation,
    # so an item being privately overridden hides the whole publication, even
    # for the workspace owner browsing the public URL. Owners can always
    # navigate via the workspace UI.
    for item in stash["items"]:
        ok = await permission_service.check_access(
            item["object_type"], item["object_id"], viewer_id, workspace_id=stash["workspace_id"]
        )
        if not ok:
            return None

    await pool.execute("UPDATE stashes SET view_count = view_count + 1 WHERE id = $1", stash["id"])

    ws = await pool.fetchrow(
        "SELECT w.name FROM workspaces w WHERE w.id = $1",
        stash["workspace_id"],
    )
    stash["_workspace_name"] = ws["name"] if ws else ""
    return stash


async def inline_items(stash: dict, viewer_id: UUID | None = None) -> list[dict]:
    """Resolve each Stash item into a dict with {object_type, object_id, position,
    label, inline} where inline is a type-specific payload."""
    pool = get_pool()
    out: list[dict] = []
    for item in stash["items"]:
        obj_type = item["object_type"]
        obj_id = item["object_id"]
        label = item.get("label_override") or ""
        inline: dict = {}
        if obj_type == "folder":
            folder = await pool.fetchrow("SELECT name FROM folders WHERE id = $1", obj_id)
            if folder:
                label = label or folder["name"]
                # Recursive: include every page in this folder and its
                # descendants so a shared folder behaves like a wiki section.
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
                        "page", p["id"], viewer_id, workspace_id=stash["workspace_id"]
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
        elif obj_type == "session":
            s = await pool.fetchrow(
                "SELECT id, session_id, agent_name, summary, summary_status, started_at, "
                "finished_at FROM sessions WHERE id = $1",
                obj_id,
            )
            if s:
                label = label or f"#{s['session_id']}"
                events = await pool.fetch(
                    "SELECT agent_name, event_type, tool_name, content, created_at "
                    "FROM history_events "
                    "WHERE workspace_id = $1 AND session_id = $2 "
                    "ORDER BY created_at LIMIT 200",
                    stash["workspace_id"],
                    s["session_id"],
                )
                inline = {
                    "session": {
                        "id": str(s["id"]),
                        "session_id": s["session_id"],
                        "agent_name": s["agent_name"],
                        "summary": s["summary"],
                        "summary_status": s["summary_status"],
                        "started_at": s["started_at"].isoformat() if s["started_at"] else None,
                        "finished_at": s["finished_at"].isoformat() if s["finished_at"] else None,
                        "events": [
                            {
                                "agent_name": e["agent_name"],
                                "event_type": e["event_type"],
                                "tool_name": e["tool_name"],
                                "content": e["content"],
                                "created_at": e["created_at"].isoformat(),
                            }
                            for e in events
                        ],
                    }
                }

        if not inline:
            # Object was deleted underneath the Stash; keep a readable placeholder.
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
    """Flatten a Stash's inlined items into readable markdown text."""
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
        elif obj_type == "session":
            session = inline.get("session", {})
            parts.append(f"## Session {session.get('session_id', label)}")
            if session.get("summary"):
                parts.append(str(session["summary"]))
            for event in session.get("events", []):
                content = event.get("content")
                if content:
                    parts.append(str(content))

    return "\n\n".join(parts)


async def user_can_manage(stash_id: UUID, user_id: UUID) -> bool:
    """Stash management requires either being the Stash's owner or being an
    owner/admin of the host workspace."""
    pool = get_pool()
    row = await pool.fetchrow("SELECT workspace_id, owner_id FROM stashes WHERE id = $1", stash_id)
    if not row:
        return False
    if row["owner_id"] == user_id:
        return True
    role = await workspace_service.get_member_role(row["workspace_id"], user_id)
    return role in ("owner", "admin")
