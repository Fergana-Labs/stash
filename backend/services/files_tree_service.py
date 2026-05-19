"""Files service: folders (nested) + pages, scoped to a workspace.

The hierarchy is Workspace -> Folder* -> Page; folders nest via
parent_folder_id.
"""

import asyncio
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from uuid import UUID

import asyncpg

from ..database import get_pool
from . import permission_service

logger = logging.getLogger(__name__)

# Workspace-owned page (excludes the read-only stash mirror rows).
_OWNED_PAGE_PRED = "COALESCE(metadata->>'shared_in_stash_id', '') = ''"
# All "live" reads filter both stash-mirror and trash. Every SELECT on
# pages that wants the active set uses this.
_WORKSPACE_PAGE_FILTER = f"{_OWNED_PAGE_PRED} AND deleted_at IS NULL"


async def _filter_readable(
    rows: list[dict],
    object_type: str,
    user_id: UUID,
    workspace_id: UUID | None = None,
) -> list[dict]:
    readable = []
    for row in rows:
        row_workspace_id = workspace_id or row.get("workspace_id")
        if await permission_service.check_access(
            object_type,
            row["id"],
            user_id,
            workspace_id=row_workspace_id,
        ):
            readable.append(row)
    return readable


class DuplicatePageName(Exception):
    """A page with this name already exists in the target folder."""

    def __init__(self, workspace_id: UUID, folder_id: UUID | None, name: str):
        self.workspace_id = workspace_id
        self.folder_id = folder_id
        self.name = name
        where = f"folder {folder_id}" if folder_id else "the root of the workspace"
        super().__init__(f"Page '{name}' already exists in {where}.")


class DuplicateFolderName(Exception):
    """A folder with this name already exists at the same level."""

    def __init__(self, workspace_id: UUID, parent_folder_id: UUID | None, name: str):
        self.workspace_id = workspace_id
        self.parent_folder_id = parent_folder_id
        self.name = name
        where = f"folder {parent_folder_id}" if parent_folder_id else "the root of the workspace"
        super().__init__(f"Folder '{name}' already exists in {where}.")


class FolderCycle(Exception):
    """Setting parent_folder_id would create a cycle."""


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _HTML_TAG_RE.sub(" ", html)


def _active_content(content_type: str, content_markdown: str, content_html: str) -> str:
    """Canonical text representation for hashing/embedding."""
    if content_type == "html":
        return _strip_html(content_html)
    return content_markdown


_embed_tasks: dict[UUID, asyncio.Task] = {}


def _schedule_embed(page_id: UUID, content: str) -> None:
    existing = _embed_tasks.get(page_id)
    if existing is not None and not existing.done():
        existing.cancel()
    task = asyncio.create_task(_embed_page(page_id, content))
    _embed_tasks[page_id] = task
    task.add_done_callback(
        lambda t, pid=page_id: _embed_tasks.pop(pid, None) if _embed_tasks.get(pid) is t else None
    )


# --- Folder CRUD ---


async def create_folder(
    workspace_id: UUID,
    name: str,
    created_by: UUID,
    parent_folder_id: UUID | None = None,
) -> dict:
    pool = get_pool()
    if parent_folder_id is not None:
        parent = await pool.fetchrow(
            "SELECT workspace_id FROM folders WHERE id = $1", parent_folder_id
        )
        if not parent or parent["workspace_id"] != workspace_id:
            raise ValueError("parent_folder_id does not belong to workspace")
    try:
        row = await pool.fetchrow(
            "INSERT INTO folders (workspace_id, parent_folder_id, name, created_by) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING id, workspace_id, parent_folder_id, name, created_by, created_at, updated_at",
            workspace_id,
            parent_folder_id,
            name,
            created_by,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicateFolderName(workspace_id, parent_folder_id, name) from e
    return dict(row)


async def get_folder(folder_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM folders WHERE id = $1",
        folder_id,
    )
    return dict(row) if row else None


async def list_folders(workspace_id: UUID, user_id: UUID | None = None) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM folders WHERE workspace_id = $1 ORDER BY name",
        workspace_id,
    )
    folders = [dict(r) for r in rows]
    if user_id is None:
        return folders
    return await _filter_readable(folders, "folder", user_id, workspace_id)


async def update_folder(
    folder_id: UUID,
    workspace_id: UUID,
    name: str | None = None,
    parent_folder_id: UUID | None = None,
    move_to_root: bool = False,
) -> dict | None:
    """Rename and/or reparent a folder. Cycle-checks before moving."""
    pool = get_pool()
    if (parent_folder_id is not None or move_to_root) and not move_to_root:
        await _assert_no_cycle(folder_id, parent_folder_id)

    sets, args, idx = ["updated_at = now()"], [], 1
    if name is not None:
        sets.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if move_to_root:
        sets.append("parent_folder_id = NULL")
    elif parent_folder_id is not None:
        sets.append(f"parent_folder_id = ${idx}")
        args.append(parent_folder_id)
        idx += 1
    args.append(folder_id)
    args.append(workspace_id)
    try:
        row = await pool.fetchrow(
            f"UPDATE folders SET {', '.join(sets)} "
            f"WHERE id = ${idx} AND workspace_id = ${idx + 1} "
            "RETURNING id, workspace_id, parent_folder_id, name, created_by, created_at, updated_at",
            *args,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicateFolderName(workspace_id, parent_folder_id, name or "") from e
    return dict(row) if row else None


async def delete_folder(folder_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM folders WHERE id = $1 AND workspace_id = $2",
        folder_id,
        workspace_id,
    )
    return result == "DELETE 1"


async def walk_ancestors(folder_id: UUID) -> list[dict]:
    """Return ancestor folders from the immediate parent up to the root."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT f.* FROM folders f WHERE f.id = $1"
        "  UNION ALL"
        "  SELECT f.* FROM folders f JOIN chain c ON f.id = c.parent_folder_id"
        ") SELECT id, workspace_id, parent_folder_id, name FROM chain WHERE id <> $1",
        folder_id,
    )
    return [dict(r) for r in rows]


async def _assert_no_cycle(folder_id: UUID, new_parent_id: UUID | None) -> None:
    if new_parent_id is None:
        return
    if new_parent_id == folder_id:
        raise FolderCycle("Folder cannot be its own parent")
    pool = get_pool()
    row = await pool.fetchrow(
        "WITH RECURSIVE chain AS ("
        "  SELECT id, parent_folder_id FROM folders WHERE id = $1"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id FROM folders f "
        "  JOIN chain c ON f.id = c.parent_folder_id"
        ") SELECT 1 FROM chain WHERE id = $2 LIMIT 1",
        new_parent_id,
        folder_id,
    )
    if row:
        raise FolderCycle("Move would create a cycle")


# --- Page CRUD ---


async def create_page(
    workspace_id: UUID,
    name: str,
    created_by: UUID,
    folder_id: UUID | None = None,
    content: str = "",
    metadata: dict | None = None,
    content_type: str = "markdown",
    content_html: str = "",
    html_layout: str = "responsive",
) -> dict:
    pool = get_pool()
    if folder_id is not None:
        folder = await pool.fetchrow("SELECT workspace_id FROM folders WHERE id = $1", folder_id)
        if not folder or folder["workspace_id"] != workspace_id:
            raise ValueError("folder_id does not belong to workspace")
    active = _active_content(content_type, content, content_html)
    ch = _content_hash(active)
    meta = metadata or {}
    try:
        row = await pool.fetchrow(
            "INSERT INTO pages "
            "(workspace_id, folder_id, name, content_markdown, content_html, content_type, "
            "html_layout, content_hash, metadata, created_by, updated_by) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $10) "
            "RETURNING id, workspace_id, folder_id, name, content_markdown, content_html, "
            "content_type, html_layout, content_hash, metadata, created_by, updated_by, "
            "created_at, updated_at",
            workspace_id,
            folder_id,
            name,
            content,
            content_html,
            content_type,
            html_layout,
            ch,
            meta,
            created_by,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicatePageName(workspace_id, folder_id, name) from e
    page = dict(row)
    if active:
        _schedule_embed(page["id"], active)
    return page


async def get_page(
    page_id: UUID,
    workspace_id: UUID,
    user_id: UUID | None = None,
) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, folder_id, name, content_markdown, content_html, "
        "content_type, html_layout, content_hash, metadata, "
        "created_by, updated_by, created_at, updated_at "
        f"FROM pages WHERE id = $1 AND workspace_id = $2 AND {_WORKSPACE_PAGE_FILTER}",
        page_id,
        workspace_id,
    )
    if not row:
        return None
    page = dict(row)
    if user_id is None:
        return page
    if not await permission_service.check_access("page", page_id, user_id, workspace_id):
        return None
    return page


async def get_sync_manifest(workspace_id: UUID) -> list[dict]:
    """Lightweight page info for sync diffing (no content)."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, content_hash, metadata, updated_at, folder_id "
        f"FROM pages WHERE workspace_id = $1 AND {_WORKSPACE_PAGE_FILTER} ORDER BY name",
        workspace_id,
    )
    return [dict(r) for r in rows]


MAX_UPDATE_RETRIES = 3


class ConcurrentEditError(Exception):
    def __init__(self, page: dict):
        super().__init__(f"concurrent edit on page {page.get('id')}")
        self.page = page


async def update_page(
    page_id: UUID,
    workspace_id: UUID,
    updated_by: UUID,
    name: str | None = None,
    folder_id: UUID | None = None,
    content: str | None = None,
    content_type: str | None = None,
    content_html: str | None = None,
    html_layout: str | None = None,
    move_to_root: bool = False,
    metadata: dict | None = None,
    on_conflict: Callable[[dict], Awaitable[str]] | None = None,
) -> dict | None:
    """Update a page with optimistic concurrency on content_hash."""
    pool = get_pool()
    content_changed = content is not None or content_type is not None or content_html is not None

    if folder_id is not None and not move_to_root:
        target = await pool.fetchrow("SELECT workspace_id FROM folders WHERE id = $1", folder_id)
        if not target or target["workspace_id"] != workspace_id:
            raise ValueError("folder_id does not belong to workspace")

    for attempt in range(MAX_UPDATE_RETRIES):
        expected_hash: str | None = None
        current_type: str | None = None
        if content_changed:
            current = await pool.fetchrow(
                "SELECT content_hash, content_type, content_markdown, content_html "
                f"FROM pages WHERE id = $1 AND workspace_id = $2 AND {_WORKSPACE_PAGE_FILTER}",
                page_id,
                workspace_id,
            )
            if current is None:
                return None
            expected_hash = current["content_hash"]
            current_type = current["content_type"]

        sets = ["updated_at = now()", "updated_by = $1"]
        args: list = [updated_by]
        idx = 2

        if name is not None:
            sets.append(f"name = ${idx}")
            args.append(name)
            idx += 1
        if move_to_root:
            sets.append("folder_id = NULL")
        elif folder_id is not None:
            sets.append(f"folder_id = ${idx}")
            args.append(folder_id)
            idx += 1
        if content is not None:
            sets.append(f"content_markdown = ${idx}")
            args.append(content)
            idx += 1
        if content_html is not None:
            sets.append(f"content_html = ${idx}")
            args.append(content_html)
            idx += 1
        if content_type is not None:
            sets.append(f"content_type = ${idx}")
            args.append(content_type)
            idx += 1
        if html_layout is not None:
            sets.append(f"html_layout = ${idx}")
            args.append(html_layout)
            idx += 1
        if content_changed:
            new_type = content_type or current_type or "markdown"
            new_md = (
                content if content is not None else (current["content_markdown"] if current else "")
            )
            new_html = (
                content_html
                if content_html is not None
                else (current["content_html"] if current else "")
            )
            new_active = _active_content(new_type, new_md, new_html)
            sets.append(f"content_hash = ${idx}")
            args.append(_content_hash(new_active))
            idx += 1
        if metadata is not None:
            sets.append(f"metadata = ${idx}::jsonb")
            args.append(metadata)
            idx += 1

        args.append(page_id)
        args.append(workspace_id)
        where = f"id = ${idx} AND workspace_id = ${idx + 1} AND {_WORKSPACE_PAGE_FILTER}"
        if expected_hash is not None:
            args.append(expected_hash)
            where += f" AND content_hash = ${idx + 2}"

        try:
            row = await pool.fetchrow(
                f"UPDATE pages SET {', '.join(sets)} WHERE {where} "
                "RETURNING id, workspace_id, folder_id, name, content_markdown, content_html, "
                "content_type, html_layout, content_hash, metadata, "
                "created_by, updated_by, created_at, updated_at",
                *args,
            )
        except asyncpg.UniqueViolationError as e:
            raise DuplicatePageName(workspace_id, folder_id, name or "") from e
        if row:
            page = dict(row)
            if content_changed and page["content_hash"] != expected_hash:
                active = _active_content(
                    page["content_type"], page["content_markdown"], page["content_html"]
                )
                _schedule_embed(page["id"], active)
            return page

        if expected_hash is None:
            return None

        fresh = await pool.fetchrow(
            "SELECT id, workspace_id, folder_id, name, content_markdown, content_html, "
            "content_type, html_layout, content_hash, metadata, "
            "created_by, updated_by, created_at, updated_at "
            f"FROM pages WHERE id = $1 AND workspace_id = $2 AND {_WORKSPACE_PAGE_FILTER}",
            page_id,
            workspace_id,
        )
        if fresh is None:
            return None

        fresh_page = dict(fresh)
        logger.info(
            "update_page conflict on page %s (attempt %d/%d)",
            page_id,
            attempt + 1,
            MAX_UPDATE_RETRIES,
        )
        if on_conflict is None:
            raise ConcurrentEditError(fresh_page)
        content = await on_conflict(fresh_page)
        await asyncio.sleep(0.02 * (2**attempt))

    logger.warning("update_page exhausted retries for page %s", page_id)
    fresh = await pool.fetchrow(
        "SELECT id, workspace_id, folder_id, name, content_markdown, content_html, "
        "content_type, html_layout, content_hash "
        f"FROM pages WHERE id = $1 AND workspace_id = $2 AND {_WORKSPACE_PAGE_FILTER}",
        page_id,
        workspace_id,
    )
    if fresh is None:
        return None
    raise ConcurrentEditError(dict(fresh))


async def delete_page(page_id: UUID, workspace_id: UUID, deleted_by: UUID) -> bool:
    """Soft delete: stamps deleted_at + deleted_by. Restore via restore_page."""
    pool = get_pool()
    result = await pool.execute(
        "UPDATE pages SET deleted_at = NOW(), deleted_by = $3 "
        f"WHERE id = $1 AND workspace_id = $2 AND {_OWNED_PAGE_PRED} "
        "AND deleted_at IS NULL",
        page_id,
        workspace_id,
        deleted_by,
    )
    return result == "UPDATE 1"


async def restore_page(page_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE pages SET deleted_at = NULL, deleted_by = NULL "
        f"WHERE id = $1 AND workspace_id = $2 AND {_OWNED_PAGE_PRED} "
        "AND deleted_at IS NOT NULL",
        page_id,
        workspace_id,
    )
    return result == "UPDATE 1"


async def purge_page(page_id: UUID, workspace_id: UUID) -> bool:
    """Permanent delete — only callable on a page already in trash."""
    pool = get_pool()
    result = await pool.execute(
        f"DELETE FROM pages WHERE id = $1 AND workspace_id = $2 AND {_OWNED_PAGE_PRED} "
        "AND deleted_at IS NOT NULL",
        page_id,
        workspace_id,
    )
    return result == "DELETE 1"


async def list_trashed_pages(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, folder_id, name, content_type, deleted_at, deleted_by "
        f"FROM pages WHERE workspace_id = $1 AND {_OWNED_PAGE_PRED} "
        "AND deleted_at IS NOT NULL "
        "ORDER BY deleted_at DESC",
        workspace_id,
    )
    return [dict(r) for r in rows]


# --- Listings ---


async def list_workspace_pages(workspace_id: UUID, user_id: UUID | None = None) -> list[dict]:
    """Flat list of every page in a workspace with its folder path."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT id, parent_folder_id, name, ARRAY[name]::text[] AS path "
        "  FROM folders WHERE workspace_id = $1 AND parent_folder_id IS NULL"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id, f.name, c.path || f.name "
        "  FROM folders f JOIN chain c ON f.parent_folder_id = c.id "
        "  WHERE f.workspace_id = $1"
        ") "
        "SELECT p.id, p.name, p.content_type, p.workspace_id, p.folder_id, "
        "COALESCE(c.path, ARRAY[]::text[]) AS folder_path, p.updated_at "
        "FROM pages p LEFT JOIN chain c ON c.id = p.folder_id "
        "WHERE p.workspace_id = $1 "
        "AND COALESCE(p.metadata->>'shared_in_stash_id', '') = '' "
        "ORDER BY c.path NULLS FIRST, p.name",
        workspace_id,
    )
    pages = [dict(r) for r in rows]
    if user_id is None:
        return pages
    return await _filter_readable(pages, "page", user_id, workspace_id)


async def list_user_pages(user_id: UUID) -> list[dict]:
    """Flat list of every page across every workspace the user is a member of."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT id, parent_folder_id, name, ARRAY[name]::text[] AS path, workspace_id "
        "  FROM folders WHERE parent_folder_id IS NULL"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id, f.name, c.path || f.name, f.workspace_id "
        "  FROM folders f JOIN chain c ON f.parent_folder_id = c.id"
        ") "
        "SELECT p.id, p.name, p.content_type, p.workspace_id, p.folder_id, "
        "COALESCE(c.path, ARRAY[]::text[]) AS folder_path, "
        "w.name AS workspace_name, p.updated_at "
        "FROM pages p "
        "JOIN workspaces w ON w.id = p.workspace_id "
        "JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
        "LEFT JOIN chain c ON c.id = p.folder_id "
        "WHERE wm.user_id = $1 "
        "AND COALESCE(p.metadata->>'shared_in_stash_id', '') = '' "
        "ORDER BY w.name, c.path NULLS FIRST, p.name",
        user_id,
    )
    return await _filter_readable([dict(r) for r in rows], "page", user_id)


async def list_workspace_tree(workspace_id: UUID, user_id: UUID | None = None) -> dict:
    """Nested folder tree with pages attached at each level."""
    folders = await list_folders(workspace_id, user_id)
    pool = get_pool()
    page_rows = await pool.fetch(
        "SELECT id, workspace_id, folder_id, name, content_type, created_at, updated_at "
        f"FROM pages WHERE workspace_id = $1 AND {_WORKSPACE_PAGE_FILTER} ORDER BY name",
        workspace_id,
    )

    pages = [dict(row) for row in page_rows]
    if user_id is not None:
        pages = await _filter_readable(pages, "page", user_id, workspace_id)

    folder_by_id: dict[UUID, dict] = {}
    for f in folders:
        node = dict(f)
        node["folders"] = []
        node["pages"] = []
        folder_by_id[node["id"]] = node

    root: dict = {"folders": [], "pages": []}
    for node in folder_by_id.values():
        parent = folder_by_id.get(node["parent_folder_id"]) if node["parent_folder_id"] else root
        parent["folders"].append(node)

    for page in pages:
        if page["folder_id"] and page["folder_id"] in folder_by_id:
            folder_by_id[page["folder_id"]]["pages"].append(page)
        else:
            root["pages"].append(page)
    return root


async def search_pages_fts(
    workspace_id: UUID,
    query: str,
    limit: int = 10,
    user_id: UUID | None = None,
) -> list[dict]:
    pool = get_pool()
    kw_text_expr = (
        "COALESCE((SELECT string_agg(kw, ' ') "
        "FROM jsonb_array_elements_text(COALESCE(metadata->'keywords', '[]'::jsonb)) AS kw), '')"
    )
    content_text_expr = (
        "CASE WHEN content_type = 'html' "
        "THEN regexp_replace(COALESCE(content_html, ''), '<[^>]+>', ' ', 'g') "
        "ELSE COALESCE(content_markdown, '') END"
    )
    vec_expr = (
        f"setweight(to_tsvector('english', {content_text_expr}), 'B') || "
        f"setweight(to_tsvector('english', {kw_text_expr}), 'A')"
    )
    rows = await pool.fetch(
        f"SELECT id, workspace_id, folder_id, name, content_markdown, content_html, "
        f"content_type, {content_text_expr} AS search_text, metadata, updated_at, "
        f"ts_rank({vec_expr}, websearch_to_tsquery('english', $2)) AS rank "
        f"FROM pages "
        f"WHERE workspace_id = $1 "
        f"AND {_WORKSPACE_PAGE_FILTER} "
        f"AND ({vec_expr}) @@ websearch_to_tsquery('english', $2) "
        f"ORDER BY rank DESC LIMIT $3",
        workspace_id,
        query,
        limit * 3,
    )
    pages = [dict(r) for r in rows]
    if user_id is not None:
        pages = await _filter_readable(pages, "page", user_id, workspace_id)
    return pages[:limit]


# --- Page embeddings ---


async def _embed_page(page_id: UUID, content: str) -> None:
    from . import embeddings as embedding_service

    if not embedding_service.is_configured():
        return
    embedding = await embedding_service.embed_text(content)
    pool = get_pool()
    if embedding is None:
        await pool.execute(
            "UPDATE pages SET embed_stale = TRUE WHERE id = $1",
            page_id,
        )
        return
    await pool.execute(
        "UPDATE pages SET embedding = $1, embed_stale = FALSE WHERE id = $2",
        embedding,
        page_id,
    )


async def search_pages_vector(
    workspace_id: UUID,
    query_embedding,
    limit: int = 20,
    user_id: UUID | None = None,
) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, folder_id, name, content_markdown, content_html, "
        "content_type, html_layout, metadata, "
        "created_by, updated_by, created_at, updated_at, "
        "1 - (embedding <=> $2) AS similarity "
        f"FROM pages WHERE workspace_id = $1 AND {_WORKSPACE_PAGE_FILTER} "
        "AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        workspace_id,
        query_embedding,
        limit * 3,
    )
    pages = [dict(r) for r in rows]
    if user_id is not None:
        pages = await _filter_readable(pages, "page", user_id, workspace_id)
    return pages[:limit]


# --- Folder helpers used by other services ---


async def find_or_create_root_folder(workspace_id: UUID, name: str, created_by: UUID) -> dict:
    """Idempotent: returns the named top-level folder, creating it if missing.

    Used by publish (AI Drafts) and sessions (Sessions) which auto-target a
    well-known folder.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM folders WHERE workspace_id = $1 AND parent_folder_id IS NULL AND name = $2",
        workspace_id,
        name,
    )
    if row:
        return dict(row)
    return await create_folder(workspace_id, name, created_by, parent_folder_id=None)
