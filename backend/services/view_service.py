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


_VIEW_SELECT = (
    "SELECT id, workspace_id, slug, title, description, owner_id, is_public, "
    "cover_image_url, view_count, created_at, updated_at FROM views"
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
                "is_public, cover_image_url) VALUES ($1, $2, $3, $4, $5, $6, $7) "
                f"RETURNING {', '.join(['id','workspace_id','slug','title','description','owner_id','is_public','cover_image_url','view_count','created_at','updated_at'])}",
                workspace_id,
                slug,
                title,
                description,
                owner_id,
                is_public,
                cover_image_url,
            )
            await _replace_items(conn, row["id"], items)
    return await _attach_items(dict(row))


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
        ("is_public", is_public),
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

    row = await pool.fetchrow(f"{_VIEW_SELECT} WHERE id = $1", view_id)
    return await _attach_items(dict(row))


async def delete_view(view_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM views WHERE id = $1 AND owner_id = $2", view_id, user_id
    )
    return result == "DELETE 1"


async def list_workspace_views(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        f"{_VIEW_SELECT} WHERE workspace_id = $1 ORDER BY updated_at DESC",
        workspace_id,
    )
    return [await _attach_items(dict(r)) for r in rows]


async def get_view(view_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"{_VIEW_SELECT} WHERE id = $1", view_id)
    return await _attach_items(dict(row)) if row else None


async def get_public_view(slug: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"{_VIEW_SELECT} WHERE slug = $1 AND is_public = true", slug
    )
    if not row:
        return None
    await pool.execute("UPDATE views SET view_count = view_count + 1 WHERE id = $1", row["id"])
    view = await _attach_items(dict(row))
    ws = await pool.fetchrow(
        "SELECT name, is_public FROM workspaces WHERE id = $1", view["workspace_id"]
    )
    view["_workspace_name"] = ws["name"] if ws else ""
    view["_workspace_is_public"] = bool(ws and ws["is_public"])
    return view


async def inline_items(view: dict) -> list[dict]:
    """Resolve each view_item into a dict with {object_type, object_id, position,
    label, inline} where inline is a type-specific payload."""
    pool = get_pool()
    out: list[dict] = []
    for item in view["items"]:
        obj_type = item["object_type"]
        obj_id = item["object_id"]
        label = item.get("label_override") or ""
        inline: dict = {}
        if obj_type == "notebook":
            nb = await pool.fetchrow(
                "SELECT name, description FROM notebooks WHERE id = $1", obj_id
            )
            if nb:
                label = label or nb["name"]
                pages = await pool.fetch(
                    "SELECT id, name, content_markdown, content_html, content_type, "
                    "updated_at FROM notebook_pages "
                    "WHERE notebook_id = $1 ORDER BY name",
                    obj_id,
                )
                inline = {
                    "description": nb["description"],
                    "pages": [
                        {
                            "id": str(p["id"]),
                            "name": p["name"],
                            "content_type": p["content_type"],
                            "content_markdown": p["content_markdown"],
                            "content_html": p["content_html"],
                            "updated_at": p["updated_at"].isoformat(),
                        }
                        for p in pages
                    ],
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

        out.append({
            "object_type": obj_type,
            "object_id": obj_id,
            "position": item["position"],
            "label": label,
            "inline": inline,
        })
    return out


async def fork_view(slug: str, forker_id: UUID, name: str | None = None) -> dict | None:
    """Create a new private workspace containing only the items in the view.

    Reuses the same cloning primitives as fork_workspace but scoped to the
    view's items, not the whole source workspace.
    """
    pool = get_pool()
    view_row = await pool.fetchrow(
        f"{_VIEW_SELECT} WHERE slug = $1 AND is_public = true", slug
    )
    if not view_row:
        return None
    view = await _attach_items(dict(view_row))

    source_ws = await pool.fetchrow(
        "SELECT id, name FROM workspaces WHERE id = $1", view["workspace_id"]
    )
    if not source_ws:
        return None

    new_name = name or f"{view['title']} (from {source_ws['name']})"
    invite_code = ""
    for _ in range(5):
        invite_code = secrets.token_urlsafe(6)[:8]
        if not await pool.fetchval(
            "SELECT 1 FROM workspaces WHERE invite_code = $1", invite_code
        ):
            break

    async with pool.acquire() as conn:
        async with conn.transaction():
            new_ws = await conn.fetchrow(
                "INSERT INTO workspaces (name, description, summary, creator_id, "
                "invite_code, is_public, forked_from_workspace_id) "
                "VALUES ($1, $2, $3, $4, $5, false, $6) "
                "RETURNING id, name, description, creator_id, invite_code, is_public, "
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

                if t == "notebook":
                    nb = await conn.fetchrow(
                        "SELECT name, description FROM notebooks WHERE id = $1", src_id
                    )
                    if not nb:
                        continue
                    new_nb_id = await conn.fetchval(
                        "INSERT INTO notebooks (workspace_id, name, description, created_by) "
                        "VALUES ($1, $2, $3, $4) RETURNING id",
                        new_ws_id, nb["name"], nb["description"] or "", forker_id,
                    )
                    folders = await conn.fetch(
                        "SELECT id, name FROM notebook_folders WHERE notebook_id = $1", src_id
                    )
                    folder_id_map: dict = {}
                    for f in folders:
                        new_f = await conn.fetchval(
                            "INSERT INTO notebook_folders (notebook_id, name, created_by) "
                            "VALUES ($1, $2, $3) RETURNING id",
                            new_nb_id, f["name"], forker_id,
                        )
                        folder_id_map[f["id"]] = new_f
                    pages = await conn.fetch(
<<<<<<< HEAD
                        "SELECT folder_id, name, content_markdown, content_html, "
                        "content_type, content_hash, metadata "
=======
                        "SELECT folder_id, name, content_markdown, content_hash, metadata "
>>>>>>> d95b6d5 (fix: cursor pagination crash for forks sort + position=0 bug)
                        "FROM notebook_pages WHERE notebook_id = $1",
                        src_id,
                    )
                    for p in pages:
                        await conn.execute(
                            "INSERT INTO notebook_pages "
<<<<<<< HEAD
                            "(notebook_id, folder_id, name, content_markdown, content_html, "
                            "content_type, content_hash, metadata, created_by) "
                            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
=======
                            "(notebook_id, folder_id, name, content_markdown, "
                            "content_hash, metadata, created_by) "
                            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
>>>>>>> d95b6d5 (fix: cursor pagination crash for forks sort + position=0 bug)
                            new_nb_id,
                            folder_id_map.get(p["folder_id"]) if p["folder_id"] else None,
                            p["name"],
                            p["content_markdown"] or "",
<<<<<<< HEAD
                            p["content_html"] or "",
                            p["content_type"],
=======
>>>>>>> d95b6d5 (fix: cursor pagination crash for forks sort + position=0 bug)
                            p["content_hash"],
                            p["metadata"] or {},
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
                        new_ws_id, src["name"], src["description"] or "",
                        src["columns"], src["views"], forker_id,
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
                            new_t_id, r["data"], r["row_order"], forker_id,
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
                        new_ws_id, src["created_by"], src["agent_name"],
                        src["event_type"], src["session_id"], src["tool_name"],
                        src["content"], src["metadata"], src["attachments"],
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
    row = await pool.fetchrow(
        "SELECT workspace_id, owner_id FROM views WHERE id = $1", view_id
    )
    if not row:
        return False
    if row["owner_id"] == user_id:
        return True
    role = await workspace_service.get_member_role(row["workspace_id"], user_id)
    return role in ("owner", "admin")
