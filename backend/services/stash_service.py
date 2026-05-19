"""Stashes — the privacy and sharing boundary for workspace resources."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from uuid import UUID

from ..database import get_pool
from . import files_tree_service, permission_service, storage_service, workspace_service

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _slugify(title: str) -> str:
    base = _SLUG_RE.sub("-", title.lower()).strip("-")[:64] or "stash"
    return f"{base}-{secrets.token_urlsafe(4)[:6].lower()}"


def _strip_html(html: str) -> str:
    return _HTML_TAG_RE.sub(" ", html)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


_STASH_COLS = (
    "v.id, v.workspace_id, v.slug, v.title, v.description, v.owner_id, "
    "owner_user.name AS owner_name, owner_user.display_name AS owner_display_name, "
    "v.access, "
    "v.discoverable, v.cover_image_url, v.icon_url, v.view_count, v.forked_from_stash_id, "
    "v.created_at, v.updated_at"
)
_STASH_FROM = "FROM stashes v JOIN users owner_user ON owner_user.id = v.owner_id"
_STASH_SELECT = f"SELECT {_STASH_COLS} {_STASH_FROM}"


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
    return stash["access"] == "public"


def _mark_native(stash: dict) -> dict:
    if stash.get("forked_from_stash_id"):
        return _mark_external(stash, stash["workspace_id"])
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
            _item_value(item, "object_type"),
            _item_value(item, "object_id"),
            _item_value(item, "position") if _item_value(item, "position") is not None else i,
            _item_value(item, "label_override"),
        )


def _item_value(item, name: str):
    return getattr(item, name) if hasattr(item, name) else item[name]


async def _validate_item_partition(conn, access: str, items: list, stash_id: UUID | None) -> None:
    for item in items:
        object_type = _item_value(item, "object_type")
        object_id = _item_value(item, "object_id")
        targets = await _partition_targets(conn, object_type, object_id)
        rows = []
        for target_type, target_id in targets:
            target_rows = await conn.fetch(
                "SELECT s.id, s.access FROM stashes s "
                "JOIN stash_items si ON si.stash_id = s.id "
                "WHERE si.object_type = $1 AND si.object_id = $2 "
                "AND ($3::uuid IS NULL OR s.id != $3)",
                target_type,
                target_id,
                stash_id,
            )
            rows.extend(target_rows)
        for row in rows:
            if access == "private" and row["access"] != "private":
                raise ValueError(
                    "Private Stashes can only include items that are not in workspace or public Stashes"
                )
            if access != "private" and row["access"] == "private":
                raise ValueError(
                    "Items in private Stashes cannot be added to workspace or public Stashes"
                )


async def _partition_targets(conn, object_type: str, object_id: UUID) -> list[tuple[str, UUID]]:
    targets = [(object_type, object_id)]
    if object_type == "folder":
        rows = await conn.fetch(
            "WITH RECURSIVE subtree AS ("
            "  SELECT id FROM folders WHERE id = $1"
            "  UNION ALL"
            "  SELECT f.id FROM folders f JOIN subtree s ON f.parent_folder_id = s.id"
            ") "
            "SELECT 'folder' AS object_type, id AS object_id FROM subtree "
            "UNION ALL "
            "SELECT 'page' AS object_type, p.id AS object_id FROM pages p "
            "WHERE p.folder_id IN (SELECT id FROM subtree) "
            "UNION ALL "
            "SELECT 'file' AS object_type, f.id AS object_id FROM files f "
            "WHERE f.folder_id IN (SELECT id FROM subtree)",
            object_id,
        )
        targets.extend((row["object_type"], row["object_id"]) for row in rows)
    elif object_type in {"page", "file"}:
        source_table = "pages" if object_type == "page" else "files"
        rows = await conn.fetch(
            f"WITH RECURSIVE chain AS ("
            f"  SELECT fo.id, fo.parent_folder_id FROM folders fo "
            f"  JOIN {source_table} o ON o.folder_id = fo.id WHERE o.id = $1 "
            f"  UNION ALL "
            f"  SELECT fo.id, fo.parent_folder_id FROM folders fo "
            f"  JOIN chain c ON fo.id = c.parent_folder_id"
            f") SELECT id FROM chain",
            object_id,
        )
        targets.extend(("folder", row["id"]) for row in rows)

    deduped = {}
    for target_type, target_id in targets:
        deduped[(target_type, target_id)] = None
    return list(deduped.keys())


async def _containing_targets(conn, object_type: str, object_id: UUID) -> list[tuple[str, UUID]]:
    targets = [(object_type, object_id)]
    if object_type == "folder":
        rows = await conn.fetch(
            "WITH RECURSIVE chain AS ("
            "  SELECT id, parent_folder_id FROM folders WHERE id = $1"
            "  UNION ALL"
            "  SELECT f.id, f.parent_folder_id FROM folders f "
            "  JOIN chain c ON f.id = c.parent_folder_id"
            ") SELECT id FROM chain",
            object_id,
        )
        targets.extend(("folder", row["id"]) for row in rows)
    elif object_type in {"page", "file"}:
        source_table = "pages" if object_type == "page" else "files"
        rows = await conn.fetch(
            f"WITH RECURSIVE chain AS ("
            f"  SELECT fo.id, fo.parent_folder_id FROM folders fo "
            f"  JOIN {source_table} o ON o.folder_id = fo.id WHERE o.id = $1 "
            f"  UNION ALL "
            f"  SELECT fo.id, fo.parent_folder_id FROM folders fo "
            f"  JOIN chain c ON fo.id = c.parent_folder_id"
            f") SELECT id FROM chain",
            object_id,
        )
        targets.extend(("folder", row["id"]) for row in rows)

    deduped = {}
    for target_type, target_id in targets:
        deduped[(target_type, target_id)] = None
    return list(deduped.keys())


async def create_stash(
    workspace_id: UUID,
    owner_id: UUID,
    title: str,
    description: str,
    access: str,
    discoverable: bool,
    cover_image_url: str | None,
    items: list,
    icon_url: str | None = None,
) -> dict:
    if access not in {"workspace", "private", "public"}:
        raise ValueError("Unsupported Stash access")
    if discoverable and access != "public":
        raise ValueError("Discover Stashes must be public")

    pool = get_pool()
    slug = _slugify(title)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _validate_item_partition(conn, access, items, None)
            inserted = await conn.fetchrow(
                "INSERT INTO stashes (workspace_id, slug, title, description, owner_id, "
                "access, discoverable, cover_image_url, icon_url) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
                "RETURNING id",
                workspace_id,
                slug,
                title,
                description,
                owner_id,
                access,
                discoverable,
                cover_image_url,
                icon_url,
            )
            await _replace_items(conn, inserted["id"], items)
    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.id = $1", inserted["id"])
    out = dict(row)
    return await _attach_items(out)


async def _object_title(object_type: str, object_id: UUID) -> str:
    """Best-effort human label for an underlying object.

    Used as the default title when minting a one-item Stash URL.
    """
    pool = get_pool()
    if object_type == "folder":
        row = await pool.fetchrow("SELECT name FROM folders WHERE id = $1", object_id)
    elif object_type == "page":
        row = await pool.fetchrow("SELECT name FROM pages WHERE id = $1", object_id)
    elif object_type == "table":
        row = await pool.fetchrow("SELECT name FROM tables WHERE id = $1", object_id)
    elif object_type == "file":
        row = await pool.fetchrow("SELECT name FROM files WHERE id = $1", object_id)
    elif object_type == "session":
        row = await pool.fetchrow(
            "SELECT session_id AS name FROM sessions WHERE id = $1", object_id
        )
    else:
        row = None
    return row["name"] if row else "Shared item"


async def update_stash(
    stash_id: UUID,
    user_id: UUID,
    updates: dict,
) -> dict | None:
    pool = get_pool()
    stash = await pool.fetchrow(
        "SELECT id, workspace_id, owner_id, access FROM stashes WHERE id = $1", stash_id
    )
    if not stash or not await user_can_manage(stash_id, user_id):
        return None
    access = updates.get("access")
    discoverable = updates.get("discoverable")
    items = updates.get("items") if "items" in updates else None
    next_access = access or stash["access"]
    if next_access not in {"workspace", "private", "public"}:
        raise ValueError("Unsupported Stash access")
    if discoverable and next_access != "public":
        raise ValueError("Discover Stashes must be public")
    if access and access != "public" and updates.get("discoverable") is None:
        updates["discoverable"] = False

    sets, args, idx = [], [], 1
    clearable_fields = {"cover_image_url", "icon_url"}
    for col in (
        "title",
        "description",
        "access",
        "discoverable",
        "cover_image_url",
        "icon_url",
    ):
        if col not in updates:
            continue
        val = updates[col]
        if val is None and col not in clearable_fields:
            continue
        sets.append(f"{col} = ${idx}")
        args.append(val)
        idx += 1

    async with pool.acquire() as conn:
        async with conn.transaction():
            partition_items = items
            if partition_items is None and access is not None:
                partition_items = await conn.fetch(
                    "SELECT object_type, object_id FROM stash_items WHERE stash_id = $1",
                    stash_id,
                )
            if partition_items is not None:
                await _validate_item_partition(conn, next_access, partition_items, stash_id)
            if items is not None:
                sets.append("updated_at = now()")
            if sets:
                args.append(stash_id)
                await conn.execute(
                    f"UPDATE stashes SET {', '.join(sets)} WHERE id = ${idx}",
                    *args,
                )
            if items is not None:
                await _replace_items(conn, stash_id, items)

    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.id = $1", stash_id)
    return await _attach_items(dict(row))


async def add_sessions_to_stash(
    *,
    stash_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    session_ids: list[str],
) -> None:
    if not session_ids:
        return
    if not await user_can_manage(stash_id, user_id):
        raise ValueError("Not allowed to manage this Stash")

    pool = get_pool()
    stash = await pool.fetchrow(
        "SELECT id, workspace_id FROM stashes WHERE id = $1",
        stash_id,
    )
    if not stash or stash["workspace_id"] != workspace_id:
        raise ValueError("Default Stash must be in this workspace")

    rows = await pool.fetch(
        "SELECT id, session_id FROM sessions "
        "WHERE workspace_id = $1 AND session_id = ANY($2::varchar[])",
        workspace_id,
        session_ids,
    )
    if len(rows) != len(set(session_ids)):
        raise ValueError("One or more sessions were not materialized")

    start_position = await pool.fetchval(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM stash_items WHERE stash_id = $1",
        stash_id,
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            for offset, row in enumerate(rows):
                await conn.execute(
                    "INSERT INTO stash_items "
                    "(stash_id, object_type, object_id, position, label_override) "
                    "VALUES ($1, 'session', $2, $3, $4) "
                    "ON CONFLICT (stash_id, object_type, object_id) DO NOTHING",
                    stash_id,
                    row["id"],
                    start_position + offset,
                    row["session_id"],
                )


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
    where = ["v.access = 'public'", "v.discoverable = true"]
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
        f"v.access, v.discoverable, v.cover_image_url, v.icon_url, v.view_count, "
        f"v.created_at, v.updated_at, "
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
                    "access": stash["access"],
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


async def _filter_readable_stashes(stashes: list[dict], user_id: UUID | None) -> list[dict]:
    readable = []
    for stash in stashes:
        if await user_can_read(stash["id"], user_id):
            readable.append(stash)
    return readable


async def list_workspace_stashes(
    workspace_id: UUID,
    user_id: UUID | None = None,
) -> list[dict]:
    pool = get_pool()
    native_rows = await pool.fetch(
        f"{_STASH_SELECT} WHERE v.workspace_id = $1 ORDER BY updated_at DESC",
        workspace_id,
    )
    native = [_mark_native(await _attach_items(dict(row))) for row in native_rows]
    return await _filter_readable_stashes(native, user_id)


async def _fork_page(
    conn,
    source_page_id: UUID,
    *,
    workspace_id: UUID,
    folder_id: UUID | None,
    user_id: UUID,
) -> UUID:
    page = await conn.fetchrow(
        "SELECT name, content_markdown, content_html, content_type, html_layout, metadata "
        "FROM pages WHERE id = $1",
        source_page_id,
    )
    if not page:
        raise ValueError("Stash item page not found")

    metadata = dict(page["metadata"] or {})
    metadata.pop("shared_in_stash_id", None)
    content_markdown = page["content_markdown"] or ""
    content_html = page["content_html"] or ""
    content_type = page["content_type"] or "markdown"
    active_content = _strip_html(content_html) if content_type == "html" else content_markdown
    row = await conn.fetchrow(
        "INSERT INTO pages "
        "(workspace_id, folder_id, name, content_markdown, content_html, content_type, "
        "html_layout, content_hash, metadata, created_by, updated_by) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $10) "
        "RETURNING id",
        workspace_id,
        folder_id,
        page["name"],
        content_markdown,
        content_html,
        content_type,
        page["html_layout"] or "responsive",
        _content_hash(active_content),
        metadata,
        user_id,
    )
    return row["id"]


async def _fork_table(conn, source_table_id: UUID, *, workspace_id: UUID, user_id: UUID) -> UUID:
    table = await conn.fetchrow(
        "SELECT name, description, columns, views, embedding_config FROM tables WHERE id = $1",
        source_table_id,
    )
    if not table:
        raise ValueError("Stash item table not found")

    new_table = await conn.fetchrow(
        "INSERT INTO tables "
        "(workspace_id, name, description, columns, views, embedding_config, created_by, updated_by) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $7) RETURNING id",
        workspace_id,
        table["name"],
        table["description"],
        table["columns"],
        table["views"],
        table["embedding_config"],
        user_id,
    )
    rows = await conn.fetch(
        "SELECT data, row_order FROM table_rows WHERE table_id = $1 ORDER BY row_order",
        source_table_id,
    )
    for row in rows:
        await conn.execute(
            "INSERT INTO table_rows (table_id, data, row_order, created_by, updated_by) "
            "VALUES ($1, $2, $3, $4, $4)",
            new_table["id"],
            row["data"],
            row["row_order"],
            user_id,
        )
    return new_table["id"]


async def _fork_file(
    conn,
    source_file_id: UUID,
    *,
    workspace_id: UUID,
    folder_id: UUID | None,
    user_id: UUID,
) -> UUID:
    file = await conn.fetchrow(
        "SELECT name, content_type, size_bytes, storage_key, extracted_text, extraction_status, "
        "extraction_error, extraction_attempts, linked_table_id FROM files WHERE id = $1",
        source_file_id,
    )
    if not file:
        raise ValueError("Stash item file not found")

    linked_table_id = None
    if file["linked_table_id"]:
        linked_table_id = await _fork_table(
            conn,
            file["linked_table_id"],
            workspace_id=workspace_id,
            user_id=user_id,
        )

    new_file = await conn.fetchrow(
        "INSERT INTO files "
        "(workspace_id, folder_id, name, content_type, size_bytes, storage_key, uploaded_by, "
        "extracted_text, extraction_status, extraction_error, extraction_attempts, linked_table_id) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING id",
        workspace_id,
        folder_id,
        file["name"],
        file["content_type"],
        file["size_bytes"],
        file["storage_key"],
        user_id,
        file["extracted_text"],
        file["extraction_status"],
        file["extraction_error"],
        file["extraction_attempts"],
        linked_table_id,
    )
    return new_file["id"]


async def _fork_folder(
    conn,
    source_folder_id: UUID,
    *,
    workspace_id: UUID,
    parent_folder_id: UUID | None,
    user_id: UUID,
) -> UUID:
    folder = await conn.fetchrow("SELECT name FROM folders WHERE id = $1", source_folder_id)
    if not folder:
        raise ValueError("Stash item folder not found")

    new_folder = await conn.fetchrow(
        "INSERT INTO folders (workspace_id, parent_folder_id, name, created_by) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        workspace_id,
        parent_folder_id,
        folder["name"],
        user_id,
    )

    child_folders = await conn.fetch(
        "SELECT id FROM folders WHERE parent_folder_id = $1 ORDER BY name, id",
        source_folder_id,
    )
    for child in child_folders:
        await _fork_folder(
            conn,
            child["id"],
            workspace_id=workspace_id,
            parent_folder_id=new_folder["id"],
            user_id=user_id,
        )

    pages = await conn.fetch(
        "SELECT id FROM pages WHERE folder_id = $1 ORDER BY name, id",
        source_folder_id,
    )
    for page in pages:
        await _fork_page(
            conn,
            page["id"],
            workspace_id=workspace_id,
            folder_id=new_folder["id"],
            user_id=user_id,
        )

    files = await conn.fetch(
        "SELECT id FROM files WHERE folder_id = $1 ORDER BY name, id",
        source_folder_id,
    )
    for file in files:
        await _fork_file(
            conn,
            file["id"],
            workspace_id=workspace_id,
            folder_id=new_folder["id"],
            user_id=user_id,
        )

    return new_folder["id"]


async def _fork_session(
    conn,
    source_session_id: UUID,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> UUID:
    session = await conn.fetchrow(
        "SELECT workspace_id, session_id, agent_name, cwd, summary, summary_status, files_touched, "
        "started_at, finished_at, created_by FROM sessions WHERE id = $1",
        source_session_id,
    )
    if not session:
        raise ValueError("Stash item session not found")

    forked_session_id = f"{session['session_id']}-fork-{source_session_id.hex[:8]}"
    new_session = await conn.fetchrow(
        "INSERT INTO sessions "
        "(workspace_id, session_id, agent_name, cwd, summary, summary_status, files_touched, "
        "started_at, finished_at, created_by) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10) RETURNING id",
        workspace_id,
        forked_session_id,
        session["agent_name"],
        session["cwd"],
        session["summary"],
        session["summary_status"],
        session["files_touched"],
        session["started_at"],
        session["finished_at"],
        session["created_by"] or user_id,
    )

    events = await conn.fetch(
        "SELECT created_by, agent_name, event_type, content, session_id, tool_name, metadata, "
        "attachments, created_at FROM history_events "
        "WHERE workspace_id = $1 AND session_id = $2 ORDER BY created_at, id",
        session["workspace_id"],
        session["session_id"],
    )
    for event in events:
        await conn.execute(
            "INSERT INTO history_events "
            "(workspace_id, created_by, agent_name, event_type, content, session_id, tool_name, "
            "metadata, attachments, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10)",
            workspace_id,
            event["created_by"] or user_id,
            event["agent_name"],
            event["event_type"],
            event["content"],
            forked_session_id,
            event["tool_name"],
            event["metadata"],
            event["attachments"],
            event["created_at"],
        )

    artifacts = await conn.fetch(
        "SELECT file_path, storage_key, size_bytes, created_at "
        "FROM session_artifacts WHERE session_id = $1 ORDER BY created_at, id",
        source_session_id,
    )
    for artifact in artifacts:
        await conn.execute(
            "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes, created_at) "
            "VALUES ($1, $2, $3, $4, $5)",
            new_session["id"],
            artifact["file_path"],
            artifact["storage_key"],
            artifact["size_bytes"],
            artifact["created_at"],
        )

    return new_session["id"]


async def _fork_object(
    conn,
    object_type: str,
    object_id: UUID,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> UUID:
    if object_type == "folder":
        return await _fork_folder(
            conn,
            object_id,
            workspace_id=workspace_id,
            parent_folder_id=None,
            user_id=user_id,
        )
    if object_type == "page":
        return await _fork_page(
            conn,
            object_id,
            workspace_id=workspace_id,
            folder_id=None,
            user_id=user_id,
        )
    if object_type == "file":
        return await _fork_file(
            conn,
            object_id,
            workspace_id=workspace_id,
            folder_id=None,
            user_id=user_id,
        )
    if object_type == "table":
        return await _fork_table(conn, object_id, workspace_id=workspace_id, user_id=user_id)
    if object_type == "session":
        return await _fork_session(conn, object_id, workspace_id=workspace_id, user_id=user_id)
    raise ValueError("Unsupported Stash item type")


async def add_external_stash(workspace_id: UUID, slug: str, added_by: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.slug = $1", slug)
    if not row:
        return None
    stash = await _attach_items(dict(row))
    if stash["workspace_id"] == workspace_id:
        return _mark_native(stash)
    if not await user_can_read(stash["id"], added_by):
        return None

    existing = await pool.fetchrow(
        f"{_STASH_SELECT} WHERE v.workspace_id = $1 AND v.forked_from_stash_id = $2",
        workspace_id,
        stash["id"],
    )
    if existing:
        from . import stash_invite_service

        await stash_invite_service.mark_invite_accepted_for_stash(
            stash_id=stash["id"],
            user_id=added_by,
            workspace_id=workspace_id,
        )
        return _mark_external(await _attach_items(dict(existing)), workspace_id)

    async with pool.acquire() as conn:
        async with conn.transaction():
            inserted = await conn.fetchrow(
                "INSERT INTO stashes "
                "(workspace_id, slug, title, description, owner_id, access, discoverable, "
                "cover_image_url, icon_url, forked_from_stash_id) "
                "VALUES ($1, $2, $3, $4, $5, 'workspace', false, $6, $7, $8) "
                "RETURNING id",
                workspace_id,
                _slugify(stash["title"]),
                stash["title"],
                stash["description"],
                added_by,
                stash["cover_image_url"],
                stash.get("icon_url"),
                stash["id"],
            )
            forked_items = []
            for item in stash["items"]:
                forked_id = await _fork_object(
                    conn,
                    item["object_type"],
                    item["object_id"],
                    workspace_id=workspace_id,
                    user_id=added_by,
                )
                forked_items.append(
                    {
                        "object_type": item["object_type"],
                        "object_id": forked_id,
                        "position": item["position"],
                        "label_override": item.get("label_override"),
                    }
                )
            await _replace_items(conn, inserted["id"], forked_items)

    from . import stash_invite_service

    await stash_invite_service.mark_invite_accepted_for_stash(
        stash_id=stash["id"],
        user_id=added_by,
        workspace_id=workspace_id,
    )
    fork = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.id = $1", inserted["id"])
    return _mark_external(await _attach_items(dict(fork)), workspace_id)


async def remove_external_stash(workspace_id: UUID, stash_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    stash = await pool.fetchrow(
        "SELECT id FROM stashes "
        "WHERE workspace_id = $1 AND id = $2 AND forked_from_stash_id IS NOT NULL",
        workspace_id,
        stash_id,
    )
    if not stash or not await user_can_manage(stash_id, user_id):
        return False
    result = await pool.execute("DELETE FROM stashes WHERE id = $1", stash_id)
    return result == "DELETE 1"


async def list_object_stashes(
    workspace_id: UUID,
    object_type: str,
    object_id: UUID,
    user_id: UUID | None = None,
) -> list[dict]:
    pool = get_pool()
    rows = []
    for target_type, target_id in await _containing_targets(pool, object_type, object_id):
        target_rows = await pool.fetch(
            f"SELECT {_STASH_COLS} {_STASH_FROM} "
            "JOIN stash_items vi ON vi.stash_id = v.id "
            "WHERE v.workspace_id = $1 AND vi.object_type = $2 AND vi.object_id = $3 "
            "ORDER BY v.updated_at DESC",
            workspace_id,
            target_type,
            target_id,
        )
        rows.extend(target_rows)

    deduped = {row["id"]: dict(row) for row in rows}
    stashes = sorted(deduped.values(), key=lambda row: row["updated_at"], reverse=True)
    return await _filter_readable_stashes([await _attach_items(row) for row in stashes], user_id)


async def get_stash(stash_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.id = $1", stash_id)
    return await _attach_items(dict(row)) if row else None


async def get_public_stash(slug: str, viewer_id: UUID | None = None) -> dict | None:
    """Resolve a Stash by slug for the given viewer (None = anonymous).

    Stashes are the privacy boundary: public Stashes render anonymously,
    workspace Stashes render for workspace members, and private Stashes render
    for users explicitly added to the Stash.
    """
    pool = get_pool()
    row = await pool.fetchrow(f"{_STASH_SELECT} WHERE v.slug = $1", slug)
    if not row:
        return None
    stash = await _attach_items(dict(row))

    if not await user_can_read(stash["id"], viewer_id):
        return None

    await pool.execute("UPDATE stashes SET view_count = view_count + 1 WHERE id = $1", stash["id"])

    ws = await pool.fetchrow(
        "SELECT w.name FROM workspaces w WHERE w.id = $1",
        stash["workspace_id"],
    )
    stash["_workspace_name"] = ws["name"] if ws else ""
    return stash


async def create_shared_page(
    stash_id: UUID,
    user_id: UUID,
    *,
    name: str,
    content: str,
    content_type: str,
    content_html: str,
    html_layout: str,
) -> dict | None:
    stash = await get_stash(stash_id)
    if not stash:
        return None
    if not await user_can_write(stash_id, user_id):
        raise PermissionError("Not allowed to edit this stash")

    page = await files_tree_service.create_page(
        stash["workspace_id"],
        name,
        user_id,
        folder_id=None,
        content=content,
        metadata={"shared_in_stash_id": str(stash_id)},
        content_type=content_type,
        content_html=content_html,
        html_layout=html_layout,
    )

    pool = get_pool()
    position = await pool.fetchval(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM stash_items WHERE stash_id = $1",
        stash_id,
    )
    await pool.execute(
        "INSERT INTO stash_items (stash_id, object_type, object_id, position, label_override) "
        "VALUES ($1, 'page', $2, $3, $4)",
        stash_id,
        page["id"],
        position,
        name,
    )
    return page


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
                # descendants so a shared folder behaves like a filesystem section.
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
                files = await pool.fetch(
                    "WITH RECURSIVE subtree AS ("
                    "  SELECT id FROM folders WHERE id = $1"
                    "  UNION ALL"
                    "  SELECT f.id FROM folders f JOIN subtree s ON f.parent_folder_id = s.id"
                    ") "
                    "SELECT f.id, f.name, f.content_type, f.size_bytes, f.storage_key, f.created_at "
                    "FROM files f WHERE f.folder_id IN (SELECT id FROM subtree) "
                    "ORDER BY f.created_at, f.name",
                    obj_id,
                )
                visible_files = []
                for f in files:
                    if await permission_service.check_access(
                        "file", f["id"], viewer_id, workspace_id=stash["workspace_id"]
                    ):
                        visible_files.append(f)
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
                    "files": [
                        {
                            "id": str(f["id"]),
                            "name": f["name"],
                            "content_type": f["content_type"],
                            "size_bytes": f["size_bytes"],
                            "url": await storage_service.get_file_url(f["storage_key"]),
                            "created_at": f["created_at"].isoformat(),
                        }
                        for f in visible_files
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
                "SELECT name, content_type, size_bytes, storage_key, created_at FROM files WHERE id = $1",
                obj_id,
            )
            if f:
                label = label or f["name"]
                inline = {
                    "name": f["name"],
                    "content_type": f["content_type"],
                    "size_bytes": f["size_bytes"],
                    "url": await storage_service.get_file_url(f["storage_key"]),
                    "created_at": f["created_at"].isoformat(),
                }
        elif obj_type == "session":
            s = await pool.fetchrow(
                "SELECT id, session_id, agent_name, summary, summary_status, files_touched, started_at, "
                "finished_at FROM sessions WHERE id = $1",
                obj_id,
            )
            if s:
                label = label or f"#{s['session_id']}"
                files_touched = s["files_touched"] or []
                if isinstance(files_touched, str):
                    files_touched = json.loads(files_touched)
                events = await pool.fetch(
                    "SELECT agent_name, event_type, tool_name, content, created_at "
                    "FROM history_events "
                    "WHERE workspace_id = $1 AND session_id = $2 "
                    "ORDER BY created_at LIMIT 200",
                    stash["workspace_id"],
                    s["session_id"],
                )
                artifacts = await pool.fetch(
                    "SELECT id, file_path, storage_key, size_bytes, created_at "
                    "FROM session_artifacts WHERE session_id = $1 ORDER BY created_at",
                    s["id"],
                )
                inline = {
                    "session": {
                        "id": str(s["id"]),
                        "session_id": s["session_id"],
                        "agent_name": s["agent_name"],
                        "summary": s["summary"],
                        "summary_status": s["summary_status"],
                        "files_touched": files_touched,
                        "started_at": s["started_at"].isoformat() if s["started_at"] else None,
                        "finished_at": s["finished_at"].isoformat() if s["finished_at"] else None,
                        "artifacts": [
                            {
                                "id": str(artifact["id"]),
                                "file_path": artifact["file_path"],
                                "size_bytes": artifact["size_bytes"],
                                "url": await storage_service.get_file_url(artifact["storage_key"]),
                                "created_at": artifact["created_at"].isoformat(),
                            }
                            for artifact in artifacts
                        ],
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
            for file in inline.get("files", []):
                parts.append(
                    f"*Attached file: {file.get('name', label)} ({file.get('content_type', 'unknown')})*\n"
                )
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
    return await user_can_write(stash_id, user_id)


async def user_can_admin(stash_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    row = await pool.fetchrow("SELECT workspace_id, owner_id FROM stashes WHERE id = $1", stash_id)
    if not row:
        return False
    if row["owner_id"] == user_id:
        return True
    member = await pool.fetchrow(
        "SELECT permission FROM stash_members WHERE stash_id = $1 AND user_id = $2",
        stash_id,
        user_id,
    )
    return bool(member and member["permission"] == "admin")


async def list_members(stash_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT sm.user_id, u.name, u.display_name, sm.permission, sm.granted_by, sm.created_at "
        "FROM stash_members sm "
        "JOIN users u ON u.id = sm.user_id "
        "WHERE sm.stash_id = $1 "
        "ORDER BY sm.created_at, u.name",
        stash_id,
    )
    return [dict(row) for row in rows]


async def add_member(
    stash_id: UUID,
    user_id: UUID,
    permission: str,
    granted_by: UUID,
) -> dict | None:
    if permission not in {"read", "write", "admin"}:
        raise ValueError("Invalid Stash permission")

    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO stash_members (stash_id, user_id, permission, granted_by) "
        "VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (stash_id, user_id) DO UPDATE "
        "SET permission = EXCLUDED.permission, granted_by = EXCLUDED.granted_by "
        "RETURNING user_id, permission, granted_by, created_at",
        stash_id,
        user_id,
        permission,
        granted_by,
    )
    if not row:
        return None
    await pool.execute("UPDATE stashes SET updated_at = now() WHERE id = $1", stash_id)

    user = await pool.fetchrow(
        "SELECT name, display_name FROM users WHERE id = $1",
        user_id,
    )
    if not user:
        return None

    from . import stash_invite_service

    await stash_invite_service.create_or_update_invite(
        stash_id=stash_id,
        recipient_user_id=user_id,
        invited_by_user_id=granted_by,
        permission=permission,
    )

    member = dict(row)
    member["name"] = user["name"]
    member["display_name"] = user["display_name"]
    return member


async def remove_member(stash_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM stash_members WHERE stash_id = $1 AND user_id = $2",
        stash_id,
        user_id,
    )
    removed = result == "DELETE 1"
    if removed:
        from . import stash_invite_service

        await stash_invite_service.delete_pending_invite(stash_id, user_id)
        await pool.execute("UPDATE stashes SET updated_at = now() WHERE id = $1", stash_id)
    return removed


async def user_can_write(stash_id: UUID, user_id: UUID) -> bool:
    """Stash writes require owner/admin rights or explicit write access."""
    pool = get_pool()
    row = await pool.fetchrow("SELECT workspace_id, owner_id FROM stashes WHERE id = $1", stash_id)
    if not row:
        return False
    if row["owner_id"] == user_id:
        return True
    member = await pool.fetchrow(
        "SELECT permission FROM stash_members WHERE stash_id = $1 AND user_id = $2",
        stash_id,
        user_id,
    )
    return bool(member and member["permission"] in ("write", "admin"))


async def user_can_read(stash_id: UUID, user_id: UUID | None) -> bool:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT workspace_id, owner_id, access FROM stashes WHERE id = $1",
        stash_id,
    )
    if not row:
        return False
    if row["access"] == "public":
        return True
    if user_id is None:
        return False
    if row["owner_id"] == user_id:
        return True
    role = await workspace_service.get_member_role(row["workspace_id"], user_id)
    member = await pool.fetchrow(
        "SELECT 1 FROM stash_members WHERE stash_id = $1 AND user_id = $2",
        stash_id,
        user_id,
    )
    if member is not None:
        return True
    if row["access"] == "workspace":
        return role is not None
    return False
