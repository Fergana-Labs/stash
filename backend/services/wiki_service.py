"""Wiki service: folders (nested) + pages, scoped to a workspace.

Replaces the old notebook_service. The hierarchy is now Workspace -> Folder*
-> Page; folders nest via parent_folder_id. Wiki links resolve workspace-wide;
plain `[[page]]` is first-match by name and `[[a/b/page]]` walks an explicit
folder path.
"""

import asyncio
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from uuid import UUID

import asyncpg

from ..database import get_pool
from . import handoff_curator

logger = logging.getLogger(__name__)


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


async def list_folders(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM folders WHERE workspace_id = $1 ORDER BY name",
        workspace_id,
    )
    return [dict(r) for r in rows]


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
            "content_hash, metadata, created_by, updated_by) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $9) "
            "RETURNING id, workspace_id, folder_id, name, content_markdown, content_html, "
            "content_type, content_hash, metadata, created_by, updated_by, "
            "created_at, updated_at",
            workspace_id,
            folder_id,
            name,
            content,
            content_html,
            content_type,
            ch,
            meta,
            created_by,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicatePageName(workspace_id, folder_id, name) from e
    page = dict(row)
    if active:
        _schedule_embed(page["id"], active)
    if content_type == "markdown" and content:
        asyncio.create_task(_update_page_links(page["id"], workspace_id, content))
    asyncio.create_task(_resolve_dangling_links(workspace_id, name, page["id"]))
    asyncio.create_task(handoff_curator.mark_stale(workspace_id))
    return page


async def get_page(page_id: UUID, workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, folder_id, name, content_markdown, content_html, "
        "content_type, content_hash, metadata, "
        "created_by, updated_by, created_at, updated_at "
        "FROM pages WHERE id = $1 AND workspace_id = $2",
        page_id,
        workspace_id,
    )
    return dict(row) if row else None


async def get_sync_manifest(workspace_id: UUID) -> list[dict]:
    """Lightweight page info for sync diffing (no content)."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, content_hash, metadata, updated_at, folder_id "
        "FROM pages WHERE workspace_id = $1 ORDER BY name",
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
                "FROM pages WHERE id = $1 AND workspace_id = $2",
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
        where = f"id = ${idx} AND workspace_id = ${idx + 1}"
        if expected_hash is not None:
            args.append(expected_hash)
            where += f" AND content_hash = ${idx + 2}"

        try:
            row = await pool.fetchrow(
                f"UPDATE pages SET {', '.join(sets)} WHERE {where} "
                "RETURNING id, workspace_id, folder_id, name, content_markdown, content_html, "
                "content_type, content_hash, metadata, "
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
                if page["content_type"] == "markdown":
                    asyncio.create_task(
                        _update_page_links(page["id"], workspace_id, page["content_markdown"])
                    )
            asyncio.create_task(handoff_curator.mark_stale(workspace_id))
            return page

        if expected_hash is None:
            return None

        fresh = await pool.fetchrow(
            "SELECT id, workspace_id, folder_id, name, content_markdown, content_html, "
            "content_type, content_hash, metadata, "
            "created_by, updated_by, created_at, updated_at "
            "FROM pages WHERE id = $1 AND workspace_id = $2",
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
        "content_type, content_hash "
        "FROM pages WHERE id = $1 AND workspace_id = $2",
        page_id,
        workspace_id,
    )
    if fresh is None:
        return None
    raise ConcurrentEditError(dict(fresh))


async def delete_page(page_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM pages WHERE id = $1 AND workspace_id = $2",
        page_id,
        workspace_id,
    )
    asyncio.create_task(handoff_curator.mark_stale(workspace_id))
    return result == "DELETE 1"


# --- Listings ---


async def list_workspace_pages(workspace_id: UUID) -> list[dict]:
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
        "SELECT p.id, p.name, p.workspace_id, p.folder_id, "
        "COALESCE(c.path, ARRAY[]::text[]) AS folder_path, p.updated_at "
        "FROM pages p LEFT JOIN chain c ON c.id = p.folder_id "
        "WHERE p.workspace_id = $1 ORDER BY c.path NULLS FIRST, p.name",
        workspace_id,
    )
    return [dict(r) for r in rows]


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
        "SELECT p.id, p.name, p.workspace_id, p.folder_id, "
        "COALESCE(c.path, ARRAY[]::text[]) AS folder_path, "
        "w.name AS workspace_name, p.updated_at "
        "FROM pages p "
        "JOIN workspaces w ON w.id = p.workspace_id "
        "JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
        "LEFT JOIN chain c ON c.id = p.folder_id "
        "WHERE wm.user_id = $1 "
        "ORDER BY w.name, c.path NULLS FIRST, p.name",
        user_id,
    )
    return [dict(r) for r in rows]


async def list_workspace_tree(workspace_id: UUID) -> dict:
    """Nested folder tree with pages attached at each level."""
    folders = await list_folders(workspace_id)
    pool = get_pool()
    page_rows = await pool.fetch(
        "SELECT id, workspace_id, folder_id, name, created_at, updated_at "
        "FROM pages WHERE workspace_id = $1 ORDER BY name",
        workspace_id,
    )

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

    for p in page_rows:
        page = dict(p)
        if page["folder_id"] and page["folder_id"] in folder_by_id:
            folder_by_id[page["folder_id"]]["pages"].append(page)
        else:
            root["pages"].append(page)
    return root


async def search_pages_fts(workspace_id: UUID, query: str, limit: int = 10) -> list[dict]:
    pool = get_pool()
    kw_text_expr = (
        "COALESCE((SELECT string_agg(kw, ' ') "
        "FROM jsonb_array_elements_text(COALESCE(metadata->'keywords', '[]'::jsonb)) AS kw), '')"
    )
    vec_expr = (
        f"setweight(to_tsvector('english', content_markdown), 'B') || "
        f"setweight(to_tsvector('english', {kw_text_expr}), 'A')"
    )
    rows = await pool.fetch(
        f"SELECT id, workspace_id, folder_id, name, content_markdown, metadata, "
        f"ts_rank({vec_expr}, websearch_to_tsquery('english', $2)) AS rank "
        f"FROM pages "
        f"WHERE workspace_id = $1 "
        f"AND ({vec_expr}) @@ websearch_to_tsquery('english', $2) "
        f"ORDER BY rank DESC LIMIT $3",
        workspace_id,
        query,
        limit,
    )
    return [dict(r) for r in rows]


# --- Wiki link parsing and management ---


# Matches [[Page Name]], [[folder/Page Name]], [[a/b/Page Name]], all with
# optional |display alias.
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _extract_wiki_links(content: str) -> list[str]:
    return list(set(_WIKI_LINK_RE.findall(content)))


async def _resolve_link_path(workspace_id: UUID, link: str) -> UUID | None:
    """Resolve [[a/b/page]] into a page id. Plain page names fall back to a
    workspace-wide first match. Path components walk the folder chain."""
    pool = get_pool()
    parts = [p.strip() for p in link.split("/") if p.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        row = await pool.fetchrow(
            "SELECT id FROM pages WHERE workspace_id = $1 AND name = $2 ORDER BY updated_at DESC LIMIT 1",
            workspace_id,
            parts[0],
        )
        return row["id"] if row else None

    *folder_parts, page_name = parts
    parent: UUID | None = None
    for fname in folder_parts:
        row = await pool.fetchrow(
            "SELECT id FROM folders "
            "WHERE workspace_id = $1 AND name = $2 "
            "AND parent_folder_id IS NOT DISTINCT FROM $3",
            workspace_id,
            fname,
            parent,
        )
        if not row:
            return None
        parent = row["id"]
    page = await pool.fetchrow(
        "SELECT id FROM pages "
        "WHERE workspace_id = $1 AND folder_id IS NOT DISTINCT FROM $2 AND name = $3",
        workspace_id,
        parent,
        page_name,
    )
    return page["id"] if page else None


async def _update_page_links(page_id: UUID, workspace_id: UUID, content: str) -> None:
    """Extract [[wiki links]] from content and refresh the page_links table."""
    try:
        pool = get_pool()
        await pool.execute(
            "DELETE FROM page_links WHERE source_page_id = $1",
            page_id,
        )
        link_names = _extract_wiki_links(content)
        if not link_names:
            return
        for link in link_names:
            target_id = await _resolve_link_path(workspace_id, link)
            if target_id and target_id != page_id:
                await pool.execute(
                    "INSERT INTO page_links (source_page_id, target_page_id, link_text) "
                    "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    page_id,
                    target_id,
                    link,
                )
    except Exception:
        logger.debug("Failed to update page links for %s", page_id, exc_info=True)


async def _resolve_dangling_links(workspace_id: UUID, page_name: str, page_id: UUID) -> None:
    """When a new page is created, find pages elsewhere in the workspace that
    reference it by name and create the missing links."""
    try:
        pool = get_pool()
        pattern = f"%[[{page_name}]]%"
        rows = await pool.fetch(
            "SELECT id, content_markdown FROM pages "
            "WHERE workspace_id = $1 AND id != $2 AND content_markdown LIKE $3",
            workspace_id,
            page_id,
            pattern,
        )
        for row in rows:
            await pool.execute(
                "INSERT INTO page_links (source_page_id, target_page_id, link_text) "
                "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                row["id"],
                page_id,
                page_name,
            )
    except Exception:
        logger.debug("Failed to resolve dangling links for %s", page_name, exc_info=True)


async def get_backlinks(page_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT np.id, np.name, np.workspace_id, pl.link_text, pl.created_at "
        "FROM page_links pl JOIN pages np ON np.id = pl.source_page_id "
        "WHERE pl.target_page_id = $1 ORDER BY np.name",
        page_id,
    )
    return [dict(r) for r in rows]


async def get_outlinks(page_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT np.id, np.name, np.workspace_id, pl.link_text, pl.created_at "
        "FROM page_links pl JOIN pages np ON np.id = pl.target_page_id "
        "WHERE pl.source_page_id = $1 ORDER BY np.name",
        page_id,
    )
    return [dict(r) for r in rows]


async def get_workspace_graph(workspace_id: UUID) -> dict:
    """Full link graph for a workspace's pages: {nodes, edges}."""
    pool = get_pool()
    pages = await pool.fetch(
        "SELECT id, name FROM pages WHERE workspace_id = $1",
        workspace_id,
    )
    nodes = [{"id": str(p["id"]), "name": p["name"]} for p in pages]
    page_ids = [p["id"] for p in pages]
    if not page_ids:
        return {"nodes": nodes, "edges": []}
    edges_rows = await pool.fetch(
        "SELECT source_page_id, target_page_id, link_text FROM page_links "
        "WHERE source_page_id = ANY($1) AND target_page_id = ANY($1)",
        page_ids,
    )
    edges = [
        {
            "source": str(e["source_page_id"]),
            "target": str(e["target_page_id"]),
            "label": e["link_text"],
        }
        for e in edges_rows
    ]
    return {"nodes": nodes, "edges": edges}


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
) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, folder_id, name, content_markdown, metadata, "
        "created_by, updated_by, created_at, updated_at, "
        "1 - (embedding <=> $2) AS similarity "
        "FROM pages WHERE workspace_id = $1 AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        workspace_id,
        query_embedding,
        limit,
    )
    return [dict(r) for r in rows]


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
