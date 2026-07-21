"""Files service: folders (nested) + pages, scoped to a user.

The hierarchy is Scope -> Folder* -> Page; folders nest via
parent_folder_id.
"""

import asyncio
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from uuid import UUID

import asyncpg
import nh3

from ..database import get_pool
from . import page_events, permission_service, security_audit_service, skill_service

logger = logging.getLogger(__name__)

MD_EXTS = (".md", ".markdown", ".mdx")
HTML_EXTS = (".html", ".htm")


def detect_page_kind(filename: str, content_type: str) -> str | None:
    """Return 'markdown' or 'html' if the upload should become a page,
    else None (treat as a binary file). Mirrors the frontend's
    isMarkdownUpload / isHtmlUpload."""
    name = filename.lower()
    ct = (content_type or "").lower()
    if ct == "text/markdown" or name.endswith(MD_EXTS):
        return "markdown"
    if "html" in ct or name.endswith(HTML_EXTS):
        return "html"
    return None


# HTML pages render in a sandboxed iframe with allow-scripts, and are served on
# public skill URLs. We strip author-supplied scripts / event handlers /
# javascript: + data:text/html URLs on write so an agent- or attacker-authored
# page can't run hostile JS for a public viewer. The trusted resize/slide
# bootstrap is injected at render time (not stored), so this never touches it.
# Inline SVG diagrams. html5ever parses these in the SVG namespace, so it
# preserves the camelCase of foreign attributes (viewBox, refX) — the allowlist
# below must match that casing, not a lowercased form.
_SVG_TAGS = {
    "svg",
    "g",
    "defs",
    "marker",
    "path",
    "circle",
    "ellipse",
    "rect",
    "line",
    "polyline",
    "polygon",
    "text",
    "tspan",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
}
_SVG_ATTRS = {
    "viewBox",
    "xmlns",
    "preserveAspectRatio",
    "transform",
    "d",
    "points",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "dx",
    "dy",
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-opacity",
    "opacity",
    "text-anchor",
    "dominant-baseline",
    "font-size",
    "font-family",
    "font-weight",
    "letter-spacing",
    "marker-start",
    "marker-mid",
    "marker-end",
    "markerWidth",
    "markerHeight",
    "markerUnits",
    "refX",
    "refY",
    "orient",
    "gradientUnits",
    "gradientTransform",
    "offset",
    "stop-color",
    "stop-opacity",
    "clip-path",
    "clip-rule",
}
_SANITIZE_TAGS = (
    nh3.ALLOWED_TAGS
    | {
        "section",
        "style",
        "div",
        "span",
        "header",
        "footer",
        "main",
        "article",
        "aside",
        "nav",
        "figure",
        "figcaption",
        "video",
        "audio",
        "source",
        "picture",
        "details",
        "summary",
        "mark",
    }
    | _SVG_TAGS
)
_SANITIZE_ATTRS = {
    "*": {"class", "id", "style", "title", "lang", "dir", "role", "width", "height"},
    "span": {"data-comment-id"},  # inline comment anchors depend on this
    "img": {"src", "alt", "loading", "srcset"},
    "a": {"href", "target", "name"},
    "video": {"src", "controls", "poster", "autoplay", "loop", "muted"},
    "audio": {"src", "controls"},
    "source": {"src", "srcset", "type", "media"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "section": {"data-slide"},
    **{tag: _SVG_ATTRS for tag in _SVG_TAGS},
}
_SANITIZE_URL_SCHEMES = {"http", "https", "mailto", "tel", "data"}


def _drop_unsafe_data_uri(tag: str, attr: str, value: str) -> str | None:
    """data: URLs are useful for inline images but a phishing/exfil vector
    elsewhere (e.g. <a href="data:text/html,…">). Keep them only on <img src>."""
    if value.strip().lower().startswith("data:") and not (tag == "img" and attr == "src"):
        return None
    return value


def _sanitize_html(html: str) -> str:
    if not html:
        return html
    return nh3.clean(
        html,
        tags=_SANITIZE_TAGS,
        attributes=_SANITIZE_ATTRS,
        url_schemes=_SANITIZE_URL_SCHEMES,
        link_rel=None,
        # <title> isn't an allowed tag, so nh3 drops the tag but keeps its text —
        # which then leaks into the body as unstyled text. Authors routinely put
        # a <title> in their HTML, so remove its content outright.
        clean_content_tags={"script", "title"},
        attribute_filter=_drop_unsafe_data_uri,
    )


# All "live" reads filter trash. Every SELECT on pages that wants the
# active set uses this.
_PAGE_FILTER = "deleted_at IS NULL"


class DuplicatePageName(Exception):
    """A page with this name already exists in the target folder."""

    def __init__(self, owner_user_id: UUID, folder_id: UUID | None, name: str):
        self.owner_user_id = owner_user_id
        self.folder_id = folder_id
        self.name = name
        where = f"folder {folder_id}" if folder_id else "the root of the scope"
        super().__init__(f"Page '{name}' already exists in {where}.")


class DuplicateFolderName(Exception):
    """A folder with this name already exists at the same level."""

    def __init__(self, owner_user_id: UUID, parent_folder_id: UUID | None, name: str):
        self.owner_user_id = owner_user_id
        self.parent_folder_id = parent_folder_id
        self.name = name
        where = f"folder {parent_folder_id}" if parent_folder_id else "the root of the scope"
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
    owner_user_id: UUID,
    name: str,
    created_by: UUID,
    parent_folder_id: UUID | None = None,
) -> dict:
    pool = get_pool()
    if parent_folder_id is not None:
        parent = await pool.fetchrow(
            "SELECT owner_user_id FROM folders WHERE id = $1", parent_folder_id
        )
        if not parent or parent["owner_user_id"] != owner_user_id:
            raise ValueError("parent_folder_id does not belong to scope")
    try:
        row = await pool.fetchrow(
            "INSERT INTO folders (owner_user_id, parent_folder_id, name, created_by) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at",
            owner_user_id,
            parent_folder_id,
            name,
            created_by,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicateFolderName(owner_user_id, parent_folder_id, name) from e
    return dict(row)


async def get_folder(folder_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM folders WHERE id = $1",
        folder_id,
    )
    return dict(row) if row else None


async def list_folders(owner_user_id: UUID, user_id: UUID | None = None) -> list[dict]:
    pool = get_pool()
    args: list = [owner_user_id]
    where = "f.owner_user_id = $1"
    if user_id is not None:
        args.append(user_id)
        where += " AND " + permission_service.readable_content_condition("folder", "f", 2)
    rows = await pool.fetch(
        "SELECT id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at "
        f"FROM folders f WHERE {where} ORDER BY name",
        *args,
    )
    return [dict(r) for r in rows]


async def get_or_create_memory_folder(owner_user_id: UUID, created_by: UUID) -> dict:
    """The reserved per-user Memory folder — its own space, not a Files folder.
    One per owner (partial unique index); created on first access."""
    pool = get_pool()
    select = (
        "SELECT id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM folders WHERE owner_user_id = $1 AND is_memory LIMIT 1"
    )
    row = await pool.fetchrow(select, owner_user_id)
    if row:
        return dict(row)
    try:
        row = await pool.fetchrow(
            "INSERT INTO folders (owner_user_id, name, created_by, is_memory) "
            "VALUES ($1, 'Memory', $2, true) "
            "RETURNING id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at",
            owner_user_id,
            created_by,
        )
        return dict(row)
    except asyncpg.UniqueViolationError:
        # Lost a race — the folder now exists.
        return dict(await pool.fetchrow(select, owner_user_id))


async def memory_subtree_folder_ids(owner_user_id: UUID) -> set[UUID]:
    """The Memory folder and all its descendants — kept out of Files surfaces."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE mtree AS ("
        "  SELECT f.id FROM folders f WHERE f.owner_user_id = $1 AND f.is_memory"
        "  UNION"
        "  SELECT f.id FROM folders f JOIN mtree m ON f.parent_folder_id = m.id"
        ") SELECT id FROM mtree",
        owner_user_id,
    )
    return {r["id"] for r in rows}


# The curator links wiki pages as `[Title](/page/<page_id>)` (markdown) or
# `href="/page/<page_id>"` (HTML layout), so any /page/<uuid> reference is a link.
_WIKI_PAGE_LINK = re.compile(
    r"/page/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.IGNORECASE
)


async def memory_wiki_graph(owner_user_id: UUID) -> dict:
    """The Memory wiki as a graph: every live page in the Memory subtree is a
    node; a page-body reference to another wiki page is an undirected edge."""
    pool = get_pool()
    folder_ids = await memory_subtree_folder_ids(owner_user_id)
    if not folder_ids:
        return {"nodes": [], "edges": []}
    rows = await pool.fetch(
        "SELECT id, name, content_markdown, content_html FROM pages "
        "WHERE folder_id = ANY($1::uuid[]) AND deleted_at IS NULL",
        list(folder_ids),
    )
    page_ids = {r["id"] for r in rows}
    edges: set[tuple[str, str]] = set()
    for r in rows:
        body = (r["content_markdown"] or "") + (r["content_html"] or "")
        for match in _WIKI_PAGE_LINK.finditer(body):
            target = UUID(match.group(1))
            if target in page_ids and target != r["id"]:
                edges.add(tuple(sorted((str(r["id"]), str(target)))))
    degree = {str(r["id"]): 0 for r in rows}
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1
    return {
        "nodes": [
            {"id": str(r["id"]), "name": r["name"], "degree": degree[str(r["id"])]} for r in rows
        ],
        "edges": [{"source": a, "target": b} for a, b in sorted(edges)],
    }


async def memory_tree(owner_user_id: UUID, created_by: UUID) -> dict:
    """The Memory wiki as a nested file-system tree — folders with pages
    attached at each level, rooted at the Memory folder (the folder itself is
    implicit; the response is its contents). Owner-only, like the graph."""
    memory = await get_or_create_memory_folder(owner_user_id, created_by)
    pool = get_pool()
    folder_rows = await pool.fetch(
        "WITH RECURSIVE mtree AS ("
        "  SELECT f.* FROM folders f WHERE f.id = $1"
        "  UNION ALL"
        "  SELECT f.* FROM folders f JOIN mtree m ON f.parent_folder_id = m.id"
        ") SELECT id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM mtree ORDER BY name",
        memory["id"],
    )
    folder_by_id: dict[UUID, dict] = {}
    for row in folder_rows:
        node = dict(row)
        node["folders"] = []
        node["pages"] = []
        folder_by_id[node["id"]] = node

    page_rows = await pool.fetch(
        "SELECT id, owner_user_id, folder_id, name, content_type, created_at, updated_at "
        "FROM pages WHERE folder_id = ANY($1::uuid[]) AND deleted_at IS NULL ORDER BY name",
        list(folder_by_id.keys()),
    )

    for node in folder_by_id.values():
        if node["id"] != memory["id"]:
            folder_by_id[node["parent_folder_id"]]["folders"].append(node)
    for row in page_rows:
        folder_by_id[row["folder_id"]]["pages"].append(dict(row))

    root = folder_by_id[memory["id"]]
    return {"folders": root["folders"], "pages": root["pages"]}


async def _assert_not_memory(folder_id: UUID, owner_user_id: UUID) -> None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT is_memory FROM folders WHERE id = $1 AND owner_user_id = $2",
        folder_id,
        owner_user_id,
    )
    if row and row["is_memory"]:
        raise ValueError("the Memory folder can't be renamed, moved, or deleted")


async def update_folder(
    folder_id: UUID,
    owner_user_id: UUID,
    name: str | None = None,
    parent_folder_id: UUID | None = None,
    move_to_root: bool = False,
) -> dict | None:
    """Rename and/or reparent a folder. Cycle-checks before moving."""
    pool = get_pool()
    await _assert_not_memory(folder_id, owner_user_id)
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
    args.append(owner_user_id)
    try:
        row = await pool.fetchrow(
            f"UPDATE folders SET {', '.join(sets)} "
            f"WHERE id = ${idx} AND owner_user_id = ${idx + 1} "
            "RETURNING id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at",
            *args,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicateFolderName(owner_user_id, parent_folder_id, name or "") from e
    return dict(row) if row else None


async def delete_folder(folder_id: UUID, owner_user_id: UUID, deleted_by: UUID) -> bool:
    """Delete a folder and everything in its subtree.

    Contents get the same treatment their own delete endpoints give them:
    pages and files are soft-deleted into trash, tables are hard-deleted,
    and skill rows cascade with their folder. Without this pass, the
    ON DELETE SET NULL foreign keys would silently strand every page, file,
    and table of the subtree at the scope root instead of deleting them.
    (Trashed pages/files still get their folder_id nulled by the FK, so a
    later restore files them at the scope root — same as restoring any item
    whose folder is gone.)
    """
    await _assert_not_memory(folder_id, owner_user_id)
    async with get_pool().acquire() as conn, conn.transaction():
        subtree = await conn.fetch(
            "WITH RECURSIVE tree AS ("
            "  SELECT id FROM folders WHERE id = $1 AND owner_user_id = $2"
            "  UNION ALL"
            "  SELECT f.id FROM folders f JOIN tree t ON f.parent_folder_id = t.id"
            ") SELECT id FROM tree",
            folder_id,
            owner_user_id,
        )
        if not subtree:
            return False
        folder_ids = [r["id"] for r in subtree]
        pages_result = await conn.execute(
            "UPDATE pages SET deleted_at = NOW(), deleted_by = $2 "
            "WHERE folder_id = ANY($1) AND deleted_at IS NULL",
            folder_ids,
            deleted_by,
        )
        files_result = await conn.execute(
            "UPDATE files SET deleted_at = NOW(), deleted_by = $2 "
            "WHERE folder_id = ANY($1) AND deleted_at IS NULL",
            folder_ids,
            deleted_by,
        )
        tables_result = await conn.execute(
            "DELETE FROM tables WHERE folder_id = ANY($1)", folder_ids
        )
        await conn.execute("DELETE FROM folders WHERE id = $1", folder_id)
    # Audited here so every front door (REST, batch, agent tools) leaves a trail.
    await security_audit_service.record_content_lifecycle_event(
        operation="deleted",
        actor_user_id=deleted_by,
        owner_user_id=owner_user_id,
        target_type="folder",
        target_id=folder_id,
        metadata={
            "folders": len(folder_ids),
            "pages_trashed": int(pages_result.split()[-1]),
            "files_trashed": int(files_result.split()[-1]),
            "tables_deleted": int(tables_result.split()[-1]),
        },
    )
    return True


async def walk_ancestors(folder_id: UUID) -> list[dict]:
    """Return ancestor folders from the immediate parent up to the root."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT f.* FROM folders f WHERE f.id = $1"
        "  UNION ALL"
        "  SELECT f.* FROM folders f JOIN chain c ON f.id = c.parent_folder_id"
        ") SELECT id, owner_user_id, parent_folder_id, name FROM chain WHERE id <> $1",
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


async def _log_page_edit(
    page_id: UUID,
    owner_user_id: UUID,
    edited_by: UUID,
    agent_name: str | None,
    session_id: str | None,
    op: str,
) -> None:
    await get_pool().execute(
        "INSERT INTO page_edits "
        "(page_id, owner_user_id, edited_by, agent_name, session_id, op) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        page_id,
        owner_user_id,
        edited_by,
        agent_name,
        session_id,
        op,
    )


async def create_page(
    owner_user_id: UUID,
    name: str,
    created_by: UUID,
    folder_id: UUID | None = None,
    content: str = "",
    metadata: dict | None = None,
    content_type: str = "markdown",
    content_html: str = "",
    html_layout: str = "responsive",
    edit_session_id: str | None = None,
    edit_agent_name: str | None = None,
) -> dict:
    pool = get_pool()
    if folder_id is not None:
        folder = await pool.fetchrow("SELECT owner_user_id FROM folders WHERE id = $1", folder_id)
        if not folder or folder["owner_user_id"] != owner_user_id:
            raise ValueError("folder_id does not belong to scope")
    content_html = _sanitize_html(content_html)
    active = _active_content(content_type, content, content_html)
    ch = _content_hash(active)
    meta = metadata or {}
    try:
        row = await pool.fetchrow(
            "INSERT INTO pages "
            "(owner_user_id, folder_id, name, content_markdown, content_html, content_type, "
            "html_layout, content_hash, metadata, created_by, updated_by, "
            "last_edit_session_id, last_edit_agent_name) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $10, $11, $12) "
            "RETURNING id, owner_user_id, folder_id, name, content_markdown, content_html, "
            "content_type, html_layout, content_hash, metadata, created_by, updated_by, "
            "last_edit_session_id, last_edit_agent_name, created_at, updated_at",
            owner_user_id,
            folder_id,
            name,
            content,
            content_html,
            content_type,
            html_layout,
            ch,
            meta,
            created_by,
            edit_session_id,
            edit_agent_name,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicatePageName(owner_user_id, folder_id, name) from e
    page = dict(row)
    await _log_page_edit(
        page["id"], owner_user_id, created_by, edit_agent_name, edit_session_id, "create"
    )
    if active:
        await _reconcile_embedded_files(page["id"], owner_user_id, created_by, active)
        _schedule_embed(page["id"], active)
    return page


async def get_page_by_id(page_id: UUID, user_id: UUID | None) -> dict | None:
    """Canonical cross-scope read: the scope comes from the row. Enforces
    check_access for the viewer (user_id None = anonymous), so a page is returned
    only to its owner, someone it's shared with, or via a public link/skill —
    this is the public read path, so it can't lean on get_page's trusted-None
    bypass, which exists for in-scope agent callers."""
    pool = get_pool()
    owner_user_id = await pool.fetchval(
        f"SELECT owner_user_id FROM pages WHERE id = $1 AND {_PAGE_FILTER}",
        page_id,
    )
    if owner_user_id is None:
        return None
    if not await permission_service.check_access("page", page_id, user_id, owner_user_id):
        return None
    return await get_page(page_id, owner_user_id, user_id)


async def get_page(
    page_id: UUID,
    owner_user_id: UUID,
    user_id: UUID | None = None,
) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, owner_user_id, folder_id, name, content_markdown, content_html, "
        "content_type, html_layout, content_hash, metadata, "
        "last_edit_session_id, last_edit_agent_name, "
        "created_by, updated_by, created_at, updated_at "
        f"FROM pages WHERE id = $1 AND owner_user_id = $2 AND {_PAGE_FILTER}",
        page_id,
        owner_user_id,
    )
    if not row:
        return None
    page = dict(row)
    if user_id is None:
        return page
    if not await permission_service.check_access("page", page_id, user_id, owner_user_id):
        return None
    return page


async def get_sync_manifest(owner_user_id: UUID) -> list[dict]:
    """Lightweight page info for sync diffing (no content)."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, content_hash, metadata, updated_at, folder_id "
        f"FROM pages WHERE owner_user_id = $1 AND {_PAGE_FILTER} ORDER BY name",
        owner_user_id,
    )
    return [dict(r) for r in rows]


MAX_UPDATE_RETRIES = 3


class ConcurrentEditError(Exception):
    def __init__(self, page: dict):
        super().__init__(f"concurrent edit on page {page.get('id')}")
        self.page = page


async def update_page(
    page_id: UUID,
    owner_user_id: UUID,
    updated_by: UUID,
    name: str | None = None,
    folder_id: UUID | None = None,
    content: str | None = None,
    content_type: str | None = None,
    content_html: str | None = None,
    html_layout: str | None = None,
    move_to_root: bool = False,
    metadata: dict | None = None,
    guard_content_hash: bool = True,
    on_conflict: Callable[[dict], Awaitable[str]] | None = None,
    edit_session_id: str | None = None,
    edit_agent_name: str | None = None,
    edit_op: str = "update",
    notify: bool = True,
) -> dict | None:
    """Update a page with optimistic concurrency on content_hash.

    When `notify` (the default for agent/REST writes, but False for the live
    editor's own Yjs->DB projection), a content change broadcasts a page-update
    event to open viewers and invalidates any persisted collab doc so a reopened
    editor reloads the fresh content instead of stale Yjs state."""
    pool = get_pool()
    if content_html is not None:
        content_html = _sanitize_html(content_html)
    content_changed = content is not None or content_type is not None or content_html is not None

    if folder_id is not None and not move_to_root:
        target = await pool.fetchrow("SELECT owner_user_id FROM folders WHERE id = $1", folder_id)
        if not target or target["owner_user_id"] != owner_user_id:
            raise ValueError("folder_id does not belong to scope")

    for attempt in range(MAX_UPDATE_RETRIES):
        expected_hash: str | None = None
        current_type: str | None = None
        if content_changed:
            current = await pool.fetchrow(
                "SELECT content_hash, content_type, content_markdown, content_html "
                f"FROM pages WHERE id = $1 AND owner_user_id = $2 AND {_PAGE_FILTER}",
                page_id,
                owner_user_id,
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
            sets.append(f"last_edit_session_id = ${idx}")
            args.append(edit_session_id)
            idx += 1
            sets.append(f"last_edit_agent_name = ${idx}")
            args.append(edit_agent_name)
            idx += 1
        if metadata is not None:
            sets.append(f"metadata = ${idx}::jsonb")
            args.append(metadata)
            idx += 1

        args.append(page_id)
        args.append(owner_user_id)
        where = f"id = ${idx} AND owner_user_id = ${idx + 1} AND {_PAGE_FILTER}"
        if expected_hash is not None and guard_content_hash:
            args.append(expected_hash)
            where += f" AND content_hash = ${idx + 2}"

        try:
            row = await pool.fetchrow(
                f"UPDATE pages SET {', '.join(sets)} WHERE {where} "
                "RETURNING id, owner_user_id, folder_id, name, content_markdown, content_html, "
                "content_type, html_layout, content_hash, metadata, "
                "last_edit_session_id, last_edit_agent_name, "
                "created_by, updated_by, created_at, updated_at",
                *args,
            )
        except asyncpg.UniqueViolationError as e:
            raise DuplicatePageName(owner_user_id, folder_id, name or "") from e
        if row:
            page = dict(row)
            if content_changed:
                await _log_page_edit(
                    page["id"], owner_user_id, updated_by, edit_agent_name, edit_session_id, edit_op
                )
                if page["content_hash"] != expected_hash:
                    active = _active_content(
                        page["content_type"], page["content_markdown"], page["content_html"]
                    )
                    await _reconcile_embedded_files(page["id"], owner_user_id, updated_by, active)
                    _schedule_embed(page["id"], active)
                if notify:
                    # An external (non-editor) write: drop stale collab state so a
                    # reopened editor reloads fresh, and tell open viewers.
                    await delete_page_collab_state(page["id"], owner_user_id)
                    page_events.publish_page_update(
                        owner_user_id, page["id"], page["content_hash"], edit_agent_name
                    )
            return page

        if expected_hash is None or not guard_content_hash:
            return None

        fresh = await pool.fetchrow(
            "SELECT id, owner_user_id, folder_id, name, content_markdown, content_html, "
            "content_type, html_layout, content_hash, metadata, "
            "created_by, updated_by, created_at, updated_at "
            f"FROM pages WHERE id = $1 AND owner_user_id = $2 AND {_PAGE_FILTER}",
            page_id,
            owner_user_id,
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
        "SELECT id, owner_user_id, folder_id, name, content_markdown, content_html, "
        "content_type, html_layout, content_hash "
        f"FROM pages WHERE id = $1 AND owner_user_id = $2 AND {_PAGE_FILTER}",
        page_id,
        owner_user_id,
    )
    if fresh is None:
        return None
    raise ConcurrentEditError(dict(fresh))


class EditMatchError(Exception):
    """`old_string` did not match exactly once in the page body."""

    def __init__(self, count: int):
        self.count = count
        super().__init__(f"old_string matched {count} times; it must match exactly once")


def _apply_edit(text: str, old_string: str, new_string: str, mode: str) -> str:
    if mode == "append":
        return text + new_string
    count = text.count(old_string)
    if count != 1:
        raise EditMatchError(count)
    return text.replace(old_string, new_string)


async def edit_page(
    page_id: UUID,
    owner_user_id: UUID,
    updated_by: UUID,
    *,
    old_string: str,
    new_string: str,
    mode: str = "replace",
    edit_session_id: str | None = None,
    edit_agent_name: str | None = None,
) -> dict | None:
    """Surgical edit of a page body: replace a unique `old_string`, or append.

    Operates on the active content field (markdown or html). `replace` mode
    fails loud — no fuzzy matching — when `old_string` matches zero or many
    times, writing nothing. Concurrent edits that leave the anchor intact are
    re-applied to the fresh body and retried; if a collaborator removes or
    duplicates the anchor, the retry raises EditMatchError rather than guessing.
    """
    for _ in range(MAX_UPDATE_RETRIES):
        page = await get_page(page_id, owner_user_id)
        if page is None:
            return None
        is_html = page["content_type"] == "html"
        field = (page["content_html"] if is_html else page["content_markdown"]) or ""
        new_text = _apply_edit(field, old_string, new_string, mode)
        edited = {"content_html": new_text} if is_html else {"content": new_text}
        try:
            result = await update_page(
                page_id=page_id,
                owner_user_id=owner_user_id,
                updated_by=updated_by,
                edit_session_id=edit_session_id,
                edit_agent_name=edit_agent_name,
                edit_op="edit",
                **edited,
            )
        except ConcurrentEditError:
            continue
        return result
    raise ConcurrentEditError(page)


# The download route a page body uses to embed a file. A file is *embedded* —
# owned by one page, absent from tree views — exactly when a live page body
# references it. _reconcile_embedded_files enforces that invariant on every
# body save, so the body is the single source of truth: no file can end up
# owned-but-unreferenced (invisible everywhere) or referenced-but-unfiled
# (cluttering the root).
_EMBED_LINK_RE = re.compile(
    r"/api/v1/me/files/"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"/download"
)


async def _reconcile_embedded_files(
    page_id: UUID, owner_user_id: UUID, actor: UUID, body: str
) -> None:
    """Sync files.owner_page_id to the embed links in a just-saved page body.

    - A referenced file that is unfiled (at root) and unowned becomes embedded.
      Files organized into folders are never claimed.
    - A referenced file this page owns comes back from trash — editor undo
      restores the link, so the bytes must follow.
    - An owned file whose link left the body is trashed (restorable)."""
    pool = get_pool()
    referenced = list({UUID(m) for m in _EMBED_LINK_RE.findall(body)})
    if referenced:
        await pool.execute(
            "UPDATE files SET owner_page_id = $1 "
            "WHERE id = ANY($2::uuid[]) AND owner_user_id = $3 "
            "AND owner_page_id IS NULL AND folder_id IS NULL AND deleted_at IS NULL",
            page_id,
            referenced,
            owner_user_id,
        )
        await pool.execute(
            "UPDATE files SET deleted_at = NULL, deleted_by = NULL "
            "WHERE id = ANY($2::uuid[]) AND owner_user_id = $3 "
            "AND owner_page_id = $1 AND deleted_at IS NOT NULL",
            page_id,
            referenced,
            owner_user_id,
        )
    await pool.execute(
        "UPDATE files SET deleted_at = NOW(), deleted_by = $4 "
        "WHERE owner_page_id = $1 AND owner_user_id = $2 AND deleted_at IS NULL "
        "AND NOT (id = ANY($3::uuid[]))",
        page_id,
        owner_user_id,
        referenced,
        actor,
    )


async def delete_page(page_id: UUID, owner_user_id: UUID, deleted_by: UUID) -> bool:
    """Soft delete: stamps deleted_at + deleted_by. Restore via restore_page.

    Embedded files are untouched: they have no lifecycle of their own while
    their page exists. A file owned by a trashed page is exactly as invisible
    as a trashed one (nothing displays it but the page), restore has nothing
    to undo, and purge_page is the destructor either way."""
    pool = get_pool()
    result = await pool.execute(
        "UPDATE pages SET deleted_at = NOW(), deleted_by = $3 "
        "WHERE id = $1 AND owner_user_id = $2  "
        "AND deleted_at IS NULL",
        page_id,
        owner_user_id,
        deleted_by,
    )
    if result != "UPDATE 1":
        return False
    # Audited here so every front door (REST, batch, agent tools) leaves a trail.
    await security_audit_service.record_content_lifecycle_event(
        operation="deleted",
        actor_user_id=deleted_by,
        owner_user_id=owner_user_id,
        target_type="page",
        target_id=page_id,
    )
    return True


async def restore_page(page_id: UUID, owner_user_id: UUID, restored_by: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE pages SET deleted_at = NULL, deleted_by = NULL "
        "WHERE id = $1 AND owner_user_id = $2  "
        "AND deleted_at IS NOT NULL",
        page_id,
        owner_user_id,
    )
    if result != "UPDATE 1":
        return False
    await security_audit_service.record_content_lifecycle_event(
        operation="restored",
        actor_user_id=restored_by,
        owner_user_id=owner_user_id,
        target_type="page",
        target_id=page_id,
    )
    return True


async def purge_page(page_id: UUID, owner_user_id: UUID) -> bool:
    """Permanent delete — only callable on a page already in trash.

    Embedded files are destroyed with the document: rows deleted and blobs
    dropped unless another row still points at the same storage key."""
    from . import files_service, storage_service

    pool = get_pool()
    in_trash = await pool.fetchval(
        "SELECT 1 FROM pages WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NOT NULL",
        page_id,
        owner_user_id,
    )
    if not in_trash:
        return False
    attachments = await pool.fetch(
        "SELECT id, storage_key FROM files WHERE owner_page_id = $1 AND owner_user_id = $2",
        page_id,
        owner_user_id,
    )
    for attachment in attachments:
        keep_blob = await files_service.storage_key_referenced_elsewhere(
            attachment["id"],
            attachment["storage_key"],
        )
        if not keep_blob:
            await storage_service.delete_file(attachment["storage_key"])
        await pool.execute(
            "DELETE FROM files WHERE id = $1 AND owner_user_id = $2",
            attachment["id"],
            owner_user_id,
        )
    result = await pool.execute(
        "DELETE FROM pages WHERE id = $1 AND owner_user_id = $2  AND deleted_at IS NOT NULL",
        page_id,
        owner_user_id,
    )
    return result == "DELETE 1"


async def delete_page_collab_state(page_id: UUID, owner_user_id: UUID) -> None:
    pool = get_pool()
    await pool.execute(
        "DELETE FROM page_collab_documents WHERE page_id = $1 AND owner_user_id = $2",
        page_id,
        owner_user_id,
    )


async def list_trashed_pages(owner_user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, owner_user_id, folder_id, name, content_type, deleted_at, deleted_by "
        "FROM pages WHERE owner_user_id = $1  "
        "AND deleted_at IS NOT NULL "
        "ORDER BY deleted_at DESC",
        owner_user_id,
    )
    return [dict(r) for r in rows]


# --- Copy / duplicate ---
#
# A duplicate is just a fresh create from a source's content, so copies inherit
# uniqueness, sanitization, and embedding for free. The top-level object copied
# directly gets a "Copy of …" name; descendants of a copied folder keep their
# names (the new folder is empty, so they can't collide).


async def create_page_unique(
    owner_user_id: UUID, base_name: str, created_by: UUID, folder_id: UUID | None, **content
) -> dict:
    """Create a page, appending ' (2)', ' (3)', … until the name is free in the
    target folder. Use for human-initiated creates where a collision should just
    pick the next free name rather than fail."""
    name = base_name
    n = 2
    while True:
        try:
            return await create_page(
                owner_user_id, name, created_by, folder_id=folder_id, **content
            )
        except DuplicatePageName:
            name = f"{base_name} ({n})"
            n += 1


async def _create_folder_unique(
    owner_user_id: UUID, base_name: str, created_by: UUID, parent_folder_id: UUID | None
) -> dict:
    name = base_name
    n = 2
    while True:
        try:
            return await create_folder(
                owner_user_id, name, created_by, parent_folder_id=parent_folder_id
            )
        except DuplicateFolderName:
            name = f"{base_name} ({n})"
            n += 1


def _page_content_kwargs(src: dict) -> dict:
    return {
        "content": src["content_markdown"] or "",
        "content_type": src["content_type"],
        "content_html": src["content_html"] or "",
        "html_layout": src["html_layout"],
        "metadata": src["metadata"],
    }


async def copy_page(
    page_id: UUID,
    owner_user_id: UUID,
    copied_by: UUID,
    target_folder_id: UUID | None = None,
) -> dict | None:
    """Duplicate a page as 'Copy of <name>'. Lands in the source's folder unless
    target_folder_id is given."""
    src = await get_page(page_id, owner_user_id)
    if src is None:
        return None
    folder_id = target_folder_id if target_folder_id is not None else src["folder_id"]
    return await create_page_unique(
        owner_user_id, f"Copy of {src['name']}", copied_by, folder_id, **_page_content_kwargs(src)
    )


async def copy_file(
    file_id: UUID,
    owner_user_id: UUID,
    copied_by: UUID,
    target_folder_id: UUID | None = None,
    name: str | None = None,
) -> dict | None:
    """Duplicate an uploaded file, copying its S3 blob to a fresh key. Files have
    no name-uniqueness constraint, so the name is used as-is."""
    from . import storage_service

    pool = get_pool()
    src = await pool.fetchrow(
        "SELECT name, content_type, storage_key, folder_id, extracted_text, extraction_status "
        "FROM files WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
        file_id,
        owner_user_id,
    )
    if not src:
        return None
    data = await storage_service.download_file(src["storage_key"])
    new_name = name or f"Copy of {src['name']}"
    new_key = await storage_service.upload_file(
        str(owner_user_id), new_name, data, src["content_type"]
    )
    folder_id = target_folder_id if target_folder_id is not None else src["folder_id"]
    row = await pool.fetchrow(
        "INSERT INTO files (owner_user_id, name, content_type, size_bytes, storage_key, "
        "uploaded_by, folder_id, extracted_text, extraction_status) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id, name",
        owner_user_id,
        new_name,
        src["content_type"],
        len(data),
        new_key,
        copied_by,
        folder_id,
        src["extracted_text"],
        src["extraction_status"],
    )
    return dict(row)


async def _copy_table_into(
    table_id: UUID, owner_user_id: UUID, copied_by: UUID, folder_id: UUID | None, name: str
) -> dict:
    """Clone a table's schema + rows into folder_id under `name`. Column ids are
    preserved by create_table, so existing row payloads stay valid."""
    from . import table_service

    meta = await table_service.get_table_metadata(table_id)
    new_table = await table_service.create_table(
        owner_user_id, name, meta["description"], meta["columns"], copied_by, folder_id=folder_id
    )
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT data FROM table_rows WHERE table_id = $1 ORDER BY row_order", table_id
    )
    if rows:
        await table_service.create_rows_batch(new_table["id"], [r["data"] for r in rows], copied_by)
    return new_table


async def _copy_folder_contents(
    src_folder_id: UUID, dst_folder_id: UUID, owner_user_id: UUID, copied_by: UUID
) -> None:
    pool = get_pool()
    page_rows = await pool.fetch(
        f"SELECT id FROM pages WHERE owner_user_id = $1 AND folder_id = $2 AND {_PAGE_FILTER}",
        owner_user_id,
        src_folder_id,
    )
    for p in page_rows:
        src = await get_page(p["id"], owner_user_id)
        if src:
            await create_page(
                owner_user_id,
                src["name"],
                copied_by,
                folder_id=dst_folder_id,
                **_page_content_kwargs(src),
            )

    table_rows = await pool.fetch(
        "SELECT id, name FROM tables WHERE owner_user_id = $1 AND folder_id = $2",
        owner_user_id,
        src_folder_id,
    )
    for t in table_rows:
        await _copy_table_into(t["id"], owner_user_id, copied_by, dst_folder_id, t["name"])

    file_rows = await pool.fetch(
        "SELECT id FROM files WHERE owner_user_id = $1 AND folder_id = $2 AND deleted_at IS NULL",
        owner_user_id,
        src_folder_id,
    )
    for f in file_rows:
        await copy_file(
            f["id"], owner_user_id, copied_by, target_folder_id=dst_folder_id, name=None
        )

    sub_rows = await pool.fetch(
        "SELECT id, name FROM folders WHERE owner_user_id = $1 AND parent_folder_id = $2",
        owner_user_id,
        src_folder_id,
    )
    for s in sub_rows:
        child = await create_folder(
            owner_user_id, s["name"], copied_by, parent_folder_id=dst_folder_id
        )
        await _copy_folder_contents(s["id"], child["id"], owner_user_id, copied_by)


async def copy_folder(
    folder_id: UUID,
    owner_user_id: UUID,
    copied_by: UUID,
    target_parent_id: UUID | None = None,
) -> dict | None:
    """Deep-copy a folder (subfolders, pages, tables, files) as 'Copy of <name>'.
    Inside the copy, descendants keep their original names — only the top folder
    is renamed. Copying files requires S3 storage to be configured."""
    src = await get_folder(folder_id)
    if not src or src["owner_user_id"] != owner_user_id:
        return None
    parent = target_parent_id if target_parent_id is not None else src["parent_folder_id"]
    if parent is not None:
        await _assert_no_cycle(folder_id, parent)
    new_root = await _create_folder_unique(
        owner_user_id, f"Copy of {src['name']}", copied_by, parent
    )
    await _copy_folder_contents(folder_id, new_root["id"], owner_user_id, copied_by)
    return new_root


# --- Listings ---


async def list_scope_pages(owner_user_id: UUID, user_id: UUID | None = None) -> list[dict]:
    """Flat list of every page in a scope with its folder path. Pages
    inside skill folders are excluded (they belong to the Skills surface)."""
    pool = get_pool()
    args: list = [owner_user_id]
    where = "p.owner_user_id = $1 AND p.deleted_at IS NULL"
    if user_id is not None:
        args.append(user_id)
        where += " AND " + permission_service.readable_content_condition("page", "p", 2)
    rows = await pool.fetch(
        "WITH RECURSIVE chain AS ("
        "  SELECT id, parent_folder_id, name, ARRAY[name]::text[] AS path "
        "  FROM folders WHERE owner_user_id = $1 AND parent_folder_id IS NULL"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id, f.name, c.path || f.name "
        "  FROM folders f JOIN chain c ON f.parent_folder_id = c.id "
        "  WHERE f.owner_user_id = $1"
        ") "
        "SELECT p.id, p.name, p.content_type, p.owner_user_id, p.folder_id, "
        "COALESCE(c.path, ARRAY[]::text[]) AS folder_path, p.updated_at "
        "FROM pages p LEFT JOIN chain c ON c.id = p.folder_id "
        f"WHERE {where} "
        "ORDER BY c.path NULLS FIRST, p.name",
        *args,
    )
    hidden = await skill_service.skill_subtree_folder_ids(owner_user_id)
    return [dict(r) for r in rows if r["folder_id"] is None or r["folder_id"] not in hidden]


async def list_user_pages(user_id: UUID) -> list[dict]:
    """Flat list of every page across every scope the user can access."""
    pool = get_pool()
    readable_page = permission_service.readable_content_condition("page", "p", 1)
    accessible_scopes = permission_service.accessible_scope_ids_sql(1)
    rows = await pool.fetch(
        "WITH RECURSIVE accessible_scopes AS ("
        f"  {accessible_scopes}"
        "), chain AS ("
        "  SELECT id, parent_folder_id, name, ARRAY[name]::text[] AS path, owner_user_id "
        "  FROM folders WHERE parent_folder_id IS NULL "
        "  AND owner_user_id IN (SELECT id FROM accessible_scopes)"
        "  UNION ALL"
        "  SELECT f.id, f.parent_folder_id, f.name, c.path || f.name, f.owner_user_id "
        "  FROM folders f JOIN chain c ON f.parent_folder_id = c.id"
        ") "
        "SELECT p.id, p.name, p.content_type, p.owner_user_id, p.folder_id, "
        "COALESCE(c.path, ARRAY[]::text[]) AS folder_path, "
        "owner.display_name AS owner_name, p.updated_at "
        "FROM pages p "
        "JOIN accessible_scopes aw ON aw.id = p.owner_user_id "
        "JOIN users owner ON owner.id = p.owner_user_id "
        "LEFT JOIN chain c ON c.id = p.folder_id "
        "WHERE p.deleted_at IS NULL "
        f"AND {readable_page} "
        "ORDER BY owner.display_name, c.path NULLS FIRST, p.name",
        user_id,
    )
    pages = [dict(r) for r in rows]
    hidden_by_scope: dict[UUID, set[UUID]] = {}
    for page in pages:
        scope = page["owner_user_id"]
        if scope not in hidden_by_scope:
            hidden_by_scope[scope] = await skill_service.skill_subtree_folder_ids(scope)
    return [
        p
        for p in pages
        if p["folder_id"] is None or p["folder_id"] not in hidden_by_scope[p["owner_user_id"]]
    ]


async def list_scope_tree(owner_user_id: UUID, user_id: UUID | None = None) -> dict:
    """Nested folder tree with pages attached at each level. Skill subtrees are
    excluded — Files and Skills are MECE; skill folders live in the Skills UI."""
    folders = await list_folders(owner_user_id, user_id)
    pool = get_pool()
    args: list = [owner_user_id]
    where = "p.owner_user_id = $1 AND p.deleted_at IS NULL"
    if user_id is not None:
        args.append(user_id)
        where += " AND " + permission_service.readable_content_condition("page", "p", 2)
    page_rows = await pool.fetch(
        "SELECT id, owner_user_id, folder_id, name, content_type, created_at, updated_at "
        f"FROM pages p WHERE {where} ORDER BY name",
        *args,
    )
    pages = [dict(row) for row in page_rows]

    hidden = await skill_service.skill_subtree_folder_ids(owner_user_id)
    hidden |= await memory_subtree_folder_ids(owner_user_id)
    folders = [f for f in folders if f["id"] not in hidden]
    pages = [p for p in pages if p["folder_id"] is None or p["folder_id"] not in hidden]

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
    owner_user_id: UUID,
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
    args: list = [owner_user_id, query]
    where = (
        f"p.owner_user_id = $1 "
        f"AND {_PAGE_FILTER} "
        f"AND ({vec_expr}) @@ websearch_to_tsquery('english', $2)"
    )
    if user_id is not None:
        args.append(user_id)
        where += " AND " + permission_service.readable_content_condition("page", "p", 3)
    args.append(limit)
    rows = await pool.fetch(
        f"SELECT id, owner_user_id, folder_id, name, content_markdown, content_html, "
        f"content_type, {content_text_expr} AS search_text, metadata, updated_at, "
        f"ts_rank({vec_expr}, websearch_to_tsquery('english', $2)) AS rank "
        f"FROM pages p "
        f"WHERE {where} "
        f"ORDER BY rank DESC LIMIT ${len(args)}",
        *args,
    )
    return [dict(r) for r in rows]


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
    owner_user_id: UUID,
    query_embedding,
    limit: int = 20,
    user_id: UUID | None = None,
) -> list[dict]:
    pool = get_pool()
    args: list = [owner_user_id, query_embedding]
    where = f"p.owner_user_id = $1 AND {_PAGE_FILTER} AND embedding IS NOT NULL"
    if user_id is not None:
        args.append(user_id)
        where += " AND " + permission_service.readable_content_condition("page", "p", 3)
    args.append(limit)
    rows = await pool.fetch(
        "SELECT id, owner_user_id, folder_id, name, content_markdown, content_html, "
        "content_type, html_layout, metadata, "
        "created_by, updated_by, created_at, updated_at, "
        "1 - (embedding <=> $2) AS similarity "
        f"FROM pages p WHERE {where} "
        f"ORDER BY embedding <=> $2 LIMIT ${len(args)}",
        *args,
    )
    return [dict(r) for r in rows]


# --- Folder helpers used by other services ---


async def find_or_create_root_folder(owner_user_id: UUID, name: str, created_by: UUID) -> dict:
    """Idempotent: returns the named top-level folder, creating it if missing.

    Used by publish (AI Drafts) and sessions (Sessions) which auto-target a
    well-known folder.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM folders WHERE owner_user_id = $1 AND parent_folder_id IS NULL AND name = $2",
        owner_user_id,
        name,
    )
    if row:
        return dict(row)
    try:
        return await create_folder(owner_user_id, name, created_by, parent_folder_id=None)
    except DuplicateFolderName:
        # Lost a get-or-create race (concurrent clip saves): the folder now
        # exists, so return it.
        row = await pool.fetchrow(
            "SELECT id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at "
            "FROM folders WHERE owner_user_id = $1 AND parent_folder_id IS NULL AND name = $2",
            owner_user_id,
            name,
        )
        return dict(row)


# --- Bulk folder-content replacement (skill sync + GitHub import) ---

_SUBTREE = (
    "WITH RECURSIVE subtree AS ("
    "  SELECT id FROM folders WHERE id = $1"
    "  UNION ALL"
    "  SELECT f.id FROM folders f JOIN subtree s ON f.parent_folder_id = s.id"
    ") SELECT id FROM subtree"
)


async def clear_folder_contents(root_folder_id: UUID) -> None:
    """Hard-delete everything inside the folder, keeping the root — for skill
    folders, skills.folder_id cascades on folder delete, so dropping the root
    would unpublish the skill. Pages/files folder FKs are ON DELETE SET NULL,
    so their rows must be deleted explicitly or they'd orphan into the
    scope root."""
    from . import storage_service

    pool = get_pool()
    if storage_service.is_configured():
        rows = await pool.fetch(
            f"SELECT storage_key FROM files WHERE folder_id IN ({_SUBTREE})", root_folder_id
        )
        for row in rows:
            await storage_service.delete_file(row["storage_key"])
    await pool.execute(f"DELETE FROM files WHERE folder_id IN ({_SUBTREE})", root_folder_id)
    await pool.execute(f"DELETE FROM pages WHERE folder_id IN ({_SUBTREE})", root_folder_id)
    await pool.execute(f"DELETE FROM folders WHERE id IN ({_SUBTREE}) AND id <> $1", root_folder_id)


async def write_folder_files(
    owner_user_id: UUID,
    owner_id: UUID,
    root_folder_id: UUID,
    files: list[tuple[str, bytes]],
) -> int:
    """Write (relative_path, bytes) pairs into the folder, creating subfolders
    as needed. Markdown/HTML become pages keeping their full filenames (skill
    detection requires a page named literally SKILL.md); everything else goes
    to file storage. Returns the number of items written."""
    import mimetypes

    from . import storage_service

    pool = get_pool()
    folder_ids: dict[str, UUID] = {"": root_folder_id}

    async def ensure_dir(path: str) -> UUID:
        if path in folder_ids:
            return folder_ids[path]
        parent, _, name = path.rpartition("/")
        parent_id = await ensure_dir(parent)
        folder = await create_folder(
            owner_user_id=owner_user_id,
            name=name,
            created_by=owner_id,
            parent_folder_id=parent_id,
        )
        folder_ids[path] = folder["id"]
        return folder["id"]

    written = 0
    for rel_path, blob in files:
        dir_path, _, filename = rel_path.rpartition("/")
        folder_id = await ensure_dir(dir_path)
        page_kind = detect_page_kind(filename, "")
        if page_kind is not None:
            text = blob.decode("utf-8", errors="replace")
            await create_page(
                owner_user_id=owner_user_id,
                name=filename,
                created_by=owner_id,
                folder_id=folder_id,
                content=text if page_kind == "markdown" else "",
                content_html=text if page_kind == "html" else "",
                content_type=page_kind,
            )
            written += 1
            continue
        if not storage_service.is_configured():
            logger.warning("file storage not configured; skipping binary %s", rel_path)
            continue
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        storage_key = await storage_service.upload_file(
            str(owner_user_id), filename, blob, content_type
        )
        await pool.execute(
            "INSERT INTO files (owner_user_id, folder_id, name, content_type, size_bytes, "
            "storage_key, uploaded_by) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            owner_user_id,
            folder_id,
            filename,
            content_type,
            len(blob),
            storage_key,
            owner_id,
        )
        written += 1
    return written
