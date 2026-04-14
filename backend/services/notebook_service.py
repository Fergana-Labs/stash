"""Notebook service: collection CRUD, page/folder CRUD, Yjs collaborative editing, wiki links."""

import asyncio
import hashlib
import json
import logging
import re
from uuid import UUID

from ..database import get_pool

logger = logging.getLogger(__name__)


def _content_hash(content: str) -> str:
    """SHA256 hash of page content for sync change detection."""
    return hashlib.sha256(content.encode()).hexdigest()


# --- Notebook (collection) CRUD ---


async def create_notebook(
    workspace_id: UUID | None, name: str, description: str, created_by: UUID,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO notebooks (workspace_id, name, description, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, workspace_id, name, description, created_by, created_at, updated_at",
        workspace_id, name, description, created_by,
    )
    return dict(row)


async def get_notebook(notebook_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, name, description, created_by, created_at, updated_at "
        "FROM notebooks WHERE id = $1",
        notebook_id,
    )
    return dict(row) if row else None


async def list_notebooks(workspace_id: UUID | None, user_id: UUID | None = None) -> list[dict]:
    """List notebooks. For personal notebooks, pass workspace_id=None and user_id."""
    pool = get_pool()
    if workspace_id is not None:
        rows = await pool.fetch(
            "SELECT id, workspace_id, name, description, created_by, created_at, updated_at "
            "FROM notebooks WHERE workspace_id = $1 ORDER BY name",
            workspace_id,
        )
    else:
        rows = await pool.fetch(
            "SELECT id, workspace_id, name, description, created_by, created_at, updated_at "
            "FROM notebooks WHERE workspace_id IS NULL AND created_by = $1 ORDER BY name",
            user_id,
        )
    return [dict(r) for r in rows]


async def delete_notebook(notebook_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM notebooks WHERE id = $1", notebook_id)
    return result == "DELETE 1"


async def list_all_user_notebooks(user_id: UUID) -> list[dict]:
    """All notebooks from workspaces user is member of + personal."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT n.id, n.workspace_id, n.name, n.description, "
        "n.created_by, n.created_at, n.updated_at, "
        "w.name AS workspace_name "
        "FROM notebooks n "
        "LEFT JOIN workspaces w ON w.id = n.workspace_id "
        "WHERE n.workspace_id IN ("
        "  SELECT workspace_id FROM workspace_members WHERE user_id = $1"
        ") OR (n.workspace_id IS NULL AND n.created_by = $1) "
        "ORDER BY n.updated_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


# --- Folders (within a notebook) ---


async def create_folder(notebook_id: UUID, name: str, created_by: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO notebook_folders (notebook_id, name, created_by) "
        "VALUES ($1, $2, $3) "
        "RETURNING id, notebook_id, name, created_by, created_at, updated_at",
        notebook_id, name, created_by,
    )
    return dict(row)


async def rename_folder(folder_id: UUID, notebook_id: UUID, name: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE notebook_folders SET name = $1, updated_at = now() "
        "WHERE id = $2 AND notebook_id = $3 "
        "RETURNING id, notebook_id, name, created_by, created_at, updated_at",
        name, folder_id, notebook_id,
    )
    return dict(row) if row else None


async def delete_folder(folder_id: UUID, notebook_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM notebook_folders WHERE id = $1 AND notebook_id = $2",
        folder_id, notebook_id,
    )
    return result == "DELETE 1"


# --- Pages (files within a notebook) ---


async def create_page(
    notebook_id: UUID, name: str, created_by: UUID,
    folder_id: UUID | None = None, content: str = "",
    metadata: dict | None = None,
) -> dict:
    pool = get_pool()
    ch = _content_hash(content)
    meta = metadata or {}
    row = await pool.fetchrow(
        "INSERT INTO notebook_pages "
        "(notebook_id, folder_id, name, content_markdown, content_hash, metadata, created_by, updated_by) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $7) "
        "RETURNING id, notebook_id, folder_id, name, content_markdown, content_hash, metadata, "
        "created_by, updated_by, created_at, updated_at",
        notebook_id, folder_id, name, content, ch, meta, created_by,
    )
    page = dict(row)
    # Fire-and-forget: embed page + extract wiki links
    if content:
        asyncio.create_task(_embed_page(page["id"], content))
        asyncio.create_task(_update_page_links(page["id"], notebook_id, content))
    # Re-resolve dangling links from other pages that might reference this new page
    asyncio.create_task(_resolve_dangling_links(notebook_id, name, page["id"]))
    return page


async def get_page(page_id: UUID, notebook_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, notebook_id, folder_id, name, content_markdown, content_hash, metadata, "
        "created_by, updated_by, created_at, updated_at "
        "FROM notebook_pages WHERE id = $1 AND notebook_id = $2",
        page_id, notebook_id,
    )
    return dict(row) if row else None


async def get_sync_manifest(notebook_id: UUID) -> list[dict]:
    """Return lightweight page info for sync diffing (no content bodies)."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, content_hash, metadata, updated_at "
        "FROM notebook_pages WHERE notebook_id = $1 ORDER BY name",
        notebook_id,
    )
    return [dict(r) for r in rows]


async def update_page(
    page_id: UUID, notebook_id: UUID, updated_by: UUID,
    name: str | None = None, folder_id: UUID | None = None,
    content: str | None = None, move_to_root: bool = False,
    metadata: dict | None = None,
) -> dict | None:
    pool = get_pool()
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
        sets.append(f"content_hash = ${idx}")
        args.append(_content_hash(content))
        idx += 1
    if metadata is not None:
        sets.append(f"metadata = ${idx}::jsonb")
        args.append(metadata)
        idx += 1

    args.append(page_id)
    args.append(notebook_id)
    row = await pool.fetchrow(
        f"UPDATE notebook_pages SET {', '.join(sets)} "
        f"WHERE id = ${idx} AND notebook_id = ${idx + 1} "
        "RETURNING id, notebook_id, folder_id, name, content_markdown, content_hash, metadata, "
        "created_by, updated_by, created_at, updated_at",
        *args,
    )
    if not row:
        return None
    page = dict(row)
    # Fire-and-forget: re-embed + re-extract wiki links when content changes
    if content is not None:
        asyncio.create_task(_embed_page(page["id"], content))
        asyncio.create_task(_update_page_links(page["id"], notebook_id, content))
    return page


async def delete_page(page_id: UUID, notebook_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM notebook_pages WHERE id = $1 AND notebook_id = $2",
        page_id, notebook_id,
    )
    return result == "DELETE 1"


async def list_page_tree(notebook_id: UUID) -> dict:
    """List all pages and folders in a notebook as a tree."""
    pool = get_pool()
    folders = await pool.fetch(
        "SELECT id, notebook_id, name, created_by, created_at, updated_at "
        "FROM notebook_folders WHERE notebook_id = $1 ORDER BY name",
        notebook_id,
    )
    files = await pool.fetch(
        "SELECT id, notebook_id, folder_id, name, created_at, updated_at "
        "FROM notebook_pages WHERE notebook_id = $1 ORDER BY name",
        notebook_id,
    )

    folder_map: dict[UUID, dict] = {}
    for f in folders:
        fd = dict(f)
        fd["files"] = []
        folder_map[fd["id"]] = fd

    root_files = []
    for fi in files:
        fid = dict(fi)
        if fid["folder_id"] and fid["folder_id"] in folder_map:
            folder_map[fid["folder_id"]]["files"].append(fid)
        else:
            root_files.append(fid)

    return {"folders": list(folder_map.values()), "root_files": root_files}


# --- Yjs ---


async def save_yjs_state(
    page_id: UUID, yjs_state: bytes, content_markdown: str | None = None,
) -> None:
    pool = get_pool()
    if content_markdown is not None:
        await pool.execute(
            "UPDATE notebook_pages SET yjs_state = $1, content_markdown = $2, updated_at = now() "
            "WHERE id = $3",
            yjs_state, content_markdown, page_id,
        )
    else:
        await pool.execute(
            "UPDATE notebook_pages SET yjs_state = $1, updated_at = now() WHERE id = $2",
            yjs_state, page_id,
        )


async def get_yjs_state(page_id: UUID) -> bytes | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT yjs_state FROM notebook_pages WHERE id = $1", page_id,
    )
    return row["yjs_state"] if row else None


async def get_page_markdown(page_id: UUID) -> str | None:
    """Get content_markdown for a page (used as fallback when yjs_state is NULL)."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT content_markdown FROM notebook_pages WHERE id = $1", page_id,
    )
    return row["content_markdown"] if row else None


# --- Injection query helpers ---


async def get_always_inject_pages(notebook_id: UUID) -> list[dict]:
    """Pages with metadata.auto_inject == 'always'."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, notebook_id, name, content_markdown, metadata "
        "FROM notebook_pages "
        "WHERE notebook_id = $1 AND metadata->>'auto_inject' = 'always'",
        notebook_id,
    )
    return [dict(r) for r in rows]


async def search_pages_fts(notebook_id: UUID, query: str, limit: int = 10) -> list[dict]:
    """FTS search on notebook page content + keywords (keywords weighted A, content weighted B)."""
    pool = get_pool()
    # metadata->'keywords' is a JSONB array; convert to space-separated text
    # via jsonb_array_elements_text + string_agg for proper tsvector parsing.
    kw_text_expr = (
        "COALESCE((SELECT string_agg(kw, ' ') "
        "FROM jsonb_array_elements_text(COALESCE(metadata->'keywords', '[]'::jsonb)) AS kw), '')"
    )
    vec_expr = (
        f"setweight(to_tsvector('english', content_markdown), 'B') || "
        f"setweight(to_tsvector('english', {kw_text_expr}), 'A')"
    )
    rows = await pool.fetch(
        f"SELECT id, notebook_id, name, content_markdown, metadata, "
        f"ts_rank({vec_expr}, websearch_to_tsquery('english', $2)) AS rank "
        f"FROM notebook_pages "
        f"WHERE notebook_id = $1 "
        f"AND ({vec_expr}) @@ websearch_to_tsquery('english', $2) "
        f"ORDER BY rank DESC LIMIT $3",
        notebook_id, query, limit,
    )
    return [dict(r) for r in rows]


async def update_page_injection_metadata(
    page_id: UUID, notebook_id: UUID, injected_at_iso: str,
) -> None:
    """Atomically increment inject_count and update last_injected_at in page metadata."""
    pool = get_pool()
    await pool.execute(
        "UPDATE notebook_pages SET metadata = metadata "
        "|| jsonb_build_object("
        "  'inject_count', COALESCE((metadata->>'inject_count')::int, 0) + 1, "
        "  'last_injected_at', $3::text"
        ") "
        "WHERE id = $1 AND notebook_id = $2",
        page_id, notebook_id, injected_at_iso,
    )


# --- Wiki link parsing and management ---


# Matches [[Page Name]] and [[Page Name|display text]]
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _extract_wiki_links(content: str) -> list[str]:
    """Extract page names from [[wiki links]] in content."""
    return list(set(_WIKI_LINK_RE.findall(content)))


async def _resolve_page_name(notebook_id: UUID, page_name: str) -> UUID | None:
    """Find a page by name within the same notebook."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id FROM notebook_pages WHERE notebook_id = $1 AND name = $2",
        notebook_id, page_name.strip(),
    )
    return row["id"] if row else None


async def _update_page_links(page_id: UUID, notebook_id: UUID, content: str) -> None:
    """Extract [[wiki links]] from content and update the page_links table."""
    try:
        pool = get_pool()
        # Delete existing outlinks from this page
        await pool.execute(
            "DELETE FROM page_links WHERE source_page_id = $1", page_id,
        )

        link_names = _extract_wiki_links(content)
        if not link_names:
            return

        for name in link_names:
            target_id = await _resolve_page_name(notebook_id, name)
            if target_id and target_id != page_id:
                await pool.execute(
                    "INSERT INTO page_links (source_page_id, target_page_id, link_text) "
                    "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    page_id, target_id, name,
                )
    except Exception:
        logger.debug("Failed to update page links for %s", page_id, exc_info=True)


async def _resolve_dangling_links(notebook_id: UUID, page_name: str, page_id: UUID) -> None:
    """When a new page is created, find other pages that reference it by name and create links."""
    try:
        pool = get_pool()
        # Find pages in this notebook whose content contains [[page_name]]
        pattern = f"%[[{page_name}]]%"
        rows = await pool.fetch(
            "SELECT id, content_markdown FROM notebook_pages "
            "WHERE notebook_id = $1 AND id != $2 AND content_markdown LIKE $3",
            notebook_id, page_id, pattern,
        )
        for row in rows:
            await pool.execute(
                "INSERT INTO page_links (source_page_id, target_page_id, link_text) "
                "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                row["id"], page_id, page_name,
            )
    except Exception:
        logger.debug("Failed to resolve dangling links for %s", page_name, exc_info=True)


async def get_backlinks(page_id: UUID) -> list[dict]:
    """Get pages that link TO this page."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT np.id, np.name, np.notebook_id, pl.link_text, pl.created_at "
        "FROM page_links pl JOIN notebook_pages np ON np.id = pl.source_page_id "
        "WHERE pl.target_page_id = $1 ORDER BY np.name",
        page_id,
    )
    return [dict(r) for r in rows]


async def get_outlinks(page_id: UUID) -> list[dict]:
    """Get pages that this page links TO."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT np.id, np.name, np.notebook_id, pl.link_text, pl.created_at "
        "FROM page_links pl JOIN notebook_pages np ON np.id = pl.target_page_id "
        "WHERE pl.source_page_id = $1 ORDER BY np.name",
        page_id,
    )
    return [dict(r) for r in rows]


async def get_page_graph(notebook_id: UUID) -> dict:
    """Get the full link graph for a notebook: {nodes, edges}."""
    pool = get_pool()
    # Get all pages as nodes
    pages = await pool.fetch(
        "SELECT id, name FROM notebook_pages WHERE notebook_id = $1", notebook_id,
    )
    nodes = [{"id": str(p["id"]), "name": p["name"]} for p in pages]

    # Get all links between pages in this notebook
    page_ids = [p["id"] for p in pages]
    if not page_ids:
        return {"nodes": nodes, "edges": []}

    edges_rows = await pool.fetch(
        "SELECT source_page_id, target_page_id, link_text FROM page_links "
        "WHERE source_page_id = ANY($1) AND target_page_id = ANY($1)",
        page_ids,
    )
    edges = [
        {"source": str(e["source_page_id"]), "target": str(e["target_page_id"]),
         "label": e["link_text"]}
        for e in edges_rows
    ]

    return {"nodes": nodes, "edges": edges}


# --- Page embeddings ---


async def _embed_page(page_id: UUID, content: str) -> None:
    """Fire-and-forget: embed page content and store in database."""
    try:
        from . import embedding_service
        if not embedding_service.is_configured():
            return
        embedding = await embedding_service.embed_text(content)
        if embedding is None:
            return
        pool = get_pool()
        await pool.execute(
            "UPDATE notebook_pages SET embedding = $1 WHERE id = $2",
            embedding, page_id,
        )
    except Exception:
        logger.debug("Failed to embed page %s", page_id, exc_info=True)


async def search_pages_vector(
    notebook_id: UUID, query_embedding, limit: int = 20,
) -> list[dict]:
    """Semantic search on notebook pages using pgvector."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, notebook_id, name, content_markdown, metadata, "
        "1 - (embedding <=> $2) AS similarity "
        "FROM notebook_pages WHERE notebook_id = $1 AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        notebook_id, query_embedding, limit,
    )
    return [dict(r) for r in rows]


