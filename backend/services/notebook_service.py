"""Notebook service: collection CRUD, page/folder CRUD, Yjs collaborative editing."""

import hashlib
import json
from uuid import UUID

from ..database import get_pool


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
    meta_json = json.dumps(metadata or {})
    row = await pool.fetchrow(
        "INSERT INTO notebook_pages "
        "(notebook_id, folder_id, name, content_markdown, content_hash, metadata, created_by, updated_by) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $7) "
        "RETURNING id, notebook_id, folder_id, name, content_markdown, content_hash, metadata, "
        "created_by, updated_by, created_at, updated_at",
        notebook_id, folder_id, name, content, ch, meta_json, created_by,
    )
    return dict(row)


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
        args.append(json.dumps(metadata))
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
    return dict(row) if row else None


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
    """FTS search on notebook page content."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, notebook_id, name, content_markdown, metadata, "
        "ts_rank(to_tsvector('english', content_markdown), websearch_to_tsquery('english', $2)) AS rank "
        "FROM notebook_pages "
        "WHERE notebook_id = $1 "
        "AND to_tsvector('english', content_markdown) @@ websearch_to_tsquery('english', $2) "
        "ORDER BY rank DESC LIMIT $3",
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
