"""Anonymous read endpoints for the /s/{workspace} browse surface.

Every endpoint runs the same Drive-style ACL check the authenticated routes
do, but with an optional viewer (None = anonymous). The frontend nested
routes under /s/[workspaceId]/f/[folder]/p/[page] consume these.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..auth import get_current_user_optional
from ..database import get_pool
from ..services import permission_service

router = APIRouter(prefix="/api/v1/public", tags=["public"])

llms_router = APIRouter(tags=["public"])


def _viewer(current_user: dict | None) -> UUID | None:
    return current_user["id"] if current_user else None


async def _readable_rows(
    object_type: str,
    rows,
    viewer: UUID | None,
    *,
    workspace_id: UUID | None = None,
) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        obj = dict(row)
        if await permission_service.check_access(
            object_type,
            obj["id"],
            viewer,
            workspace_id=workspace_id or obj.get("workspace_id"),
        ):
            out.append(obj)
    return out


async def _readable_pages_in_folder(folder_id: UUID, viewer: UUID | None) -> list[dict]:
    pool = get_pool()
    pages = await pool.fetch(
        "SELECT id, workspace_id, name, content_type, content_markdown, content_html, "
        "updated_at FROM pages WHERE folder_id = $1 ORDER BY created_at, name",
        folder_id,
    )
    return await _readable_rows("page", pages, viewer)


_LLMS_TXT = """# Stash

Stash is a shared memory system for AI coding agents. Workspaces contain
folders (which can nest), pages (markdown or HTML), tables, files, and
history (agent sessions). Items can be shared as Views with slugged URLs.

## For browsing agents

Any /v/{slug} or /s/{ws}/p/{page} URL returns HTML by default.
Append ?format=text to the corresponding API endpoint to get clean
markdown:

- View: GET /api/v1/views/{slug}?format=text
- Page: GET /api/v1/public/pages/{page_id}?format=text
- Folder (all pages): GET /api/v1/public/folders/{folder_id}?format=text
- Workspace overview: GET /api/v1/public/workspaces/{workspace_id}?format=text
- Stash: GET /api/v1/stashes/{slug}?format=text

## Stashes

Stashes archive a complete coding session: transcript, artifacts
(files read/written), and an AI-generated summary. Shared via /b/{slug}.

- Stash overview: GET /api/v1/stashes/{slug}?format=text
- Specific artifact: GET /api/v1/stashes/{slug}/files/{artifact_id}
- Full transcript: GET /api/v1/stashes/{slug}/transcript

All stash endpoints are anonymous-readable. No auth headers needed.

## Privacy

Items marked `private` or `inherit` (workspace-only) are never returned by
any public endpoint, regardless of how the URL is shaped.
"""


@llms_router.get("/llms.txt", include_in_schema=False)
async def llms_txt():
    return PlainTextResponse(_LLMS_TXT, media_type="text/plain")


@router.get("/workspaces/{workspace_id}")
async def public_workspace(
    workspace_id: UUID,
    format: str | None = Query(None),
    current_user: dict | None = Depends(get_current_user_optional),
):
    pool = get_pool()
    viewer = _viewer(current_user)
    if not await permission_service.check_access("workspace", workspace_id, viewer):
        raise HTTPException(status_code=404, detail="Workspace not found")

    ws = await pool.fetchrow(
        "SELECT w.id, w.name, w.summary, w.description, w.cover_image_url, "
        "EXISTS("
        "  SELECT 1 FROM object_permissions op "
        "  WHERE op.object_type = 'workspace' AND op.object_id = w.id AND op.visibility = 'public'"
        ") AS is_public, "
        "w.creator_id, u.name AS creator_name, u.display_name AS creator_display_name, "
        "w.tags, w.category, w.discoverable, w.featured, w.fork_count, "
        "w.forked_from_workspace_id, "
        "w.created_at, w.updated_at, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count, "
        "(SELECT COUNT(*) FROM pages p WHERE p.workspace_id = w.id) AS page_count, "
        "(SELECT COUNT(*) FROM tables t WHERE t.workspace_id = w.id) AS table_count, "
        "(SELECT COUNT(*) FROM files f WHERE f.workspace_id = w.id) AS file_count, "
        "(SELECT COUNT(*) FROM history_events he WHERE he.workspace_id = w.id) AS history_event_count "
        "FROM workspaces w JOIN users u ON u.id = w.creator_id WHERE w.id = $1",
        workspace_id,
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    folder_rows = await pool.fetch(
        "SELECT f.id, f.workspace_id, f.parent_folder_id, f.name, f.updated_at, "
        "(SELECT COUNT(*) FROM pages p WHERE p.folder_id = f.id) AS page_count "
        "FROM folders f WHERE f.workspace_id = $1 "
        "ORDER BY f.parent_folder_id NULLS FIRST, f.name",
        workspace_id,
    )
    root_page_rows = await pool.fetch(
        "SELECT id, workspace_id, name, updated_at FROM pages "
        "WHERE workspace_id = $1 AND folder_id IS NULL ORDER BY name",
        workspace_id,
    )
    table_rows = await pool.fetch(
        "SELECT t.id, t.workspace_id, t.name, t.updated_at, "
        "(SELECT COUNT(*) FROM table_rows tr WHERE tr.table_id = t.id) AS row_count "
        "FROM tables t WHERE t.workspace_id = $1 ORDER BY t.updated_at DESC",
        workspace_id,
    )
    file_rows = await pool.fetch(
        "SELECT id, workspace_id, name, content_type, COALESCE(size_bytes, 0) AS size_bytes, created_at "
        "FROM files WHERE workspace_id = $1 ORDER BY created_at DESC LIMIT 200",
        workspace_id,
    )
    folders = await _readable_rows("folder", folder_rows, viewer, workspace_id=workspace_id)
    for f in folders:
        f["page_count"] = len(await _readable_pages_in_folder(f["id"], viewer))
    root_pages = await _readable_rows("page", root_page_rows, viewer, workspace_id=workspace_id)
    tables = await _readable_rows("table", table_rows, viewer, workspace_id=workspace_id)
    files = await _readable_rows("file", file_rows, viewer, workspace_id=workspace_id)
    payload = {
        "workspace": dict(ws),
        "folders": folders,
        "root_pages": root_pages,
        "tables": tables,
        "files": files,
    }
    if format == "text":
        ws_d = payload["workspace"]
        lines = [f"# {ws_d['name']}", ""]
        if ws_d.get("summary"):
            lines += [ws_d["summary"], ""]
        if ws_d.get("description"):
            lines += [ws_d["description"], ""]
        if folders:
            lines.append("## Folders")
            for n in folders:
                lines.append(f"- {n['name']} ({n['page_count']} pages)")
            lines.append("")
        if root_pages:
            lines.append("## Pages")
            for p in root_pages:
                lines.append(f"- {p['name']}")
            lines.append("")
        if tables:
            lines.append("## Tables")
            for t in tables:
                lines.append(f"- {t['name']} ({t['row_count']} rows)")
            lines.append("")
        if files:
            lines.append("## Files")
            for f in files:
                lines.append(f"- {f['name']}")
            lines.append("")
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")
    return payload


@router.get("/folders/{folder_id}")
async def public_folder(
    folder_id: UUID,
    format: str | None = Query(None),
    current_user: dict | None = Depends(get_current_user_optional),
):
    pool = get_pool()
    viewer = _viewer(current_user)
    if not await permission_service.check_access("folder", folder_id, viewer):
        raise HTTPException(status_code=404, detail="Folder not found")

    folder = await pool.fetchrow(
        "SELECT id, name, parent_folder_id, workspace_id, updated_at FROM folders WHERE id = $1",
        folder_id,
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    pages = await _readable_pages_in_folder(folder_id, viewer)
    subfolders_raw = await pool.fetch(
        "SELECT id, name, workspace_id, updated_at FROM folders "
        "WHERE parent_folder_id = $1 ORDER BY name",
        folder_id,
    )
    subfolders = await _readable_rows("folder", subfolders_raw, viewer)

    if format == "text":
        lines = [f"# {folder['name']}", ""]
        for p in pages:
            lines.append(f"## {p['name']}")
            if p["content_type"] == "html":
                lines.append("_(HTML content omitted in text format)_")
            else:
                lines.append((p["content_markdown"] or "").rstrip())
            lines.append("")
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")

    return {
        "folder": dict(folder),
        "subfolders": [
            {
                "id": str(f["id"]),
                "name": f["name"],
                "updated_at": f["updated_at"].isoformat(),
            }
            for f in subfolders
        ],
        "pages": [
            {
                "id": str(p["id"]),
                "name": p["name"],
                "content_type": p["content_type"],
                "updated_at": p["updated_at"].isoformat(),
            }
            for p in pages
        ],
    }


@router.get("/pages/{page_id}")
async def public_page(
    page_id: UUID,
    format: str | None = Query(None),
    current_user: dict | None = Depends(get_current_user_optional),
):
    pool = get_pool()
    viewer = _viewer(current_user)
    if not await permission_service.check_access("page", page_id, viewer):
        raise HTTPException(status_code=404, detail="Page not found")

    page = await pool.fetchrow(
        "SELECT p.id, p.name, p.content_type, p.content_markdown, p.content_html, "
        "p.html_layout, p.folder_id, p.workspace_id, p.updated_at, "
        "f.name AS folder_name "
        "FROM pages p LEFT JOIN folders f ON f.id = p.folder_id WHERE p.id = $1",
        page_id,
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if format == "text":
        if page["content_type"] == "html":
            return PlainTextResponse(
                f"# {page['name']}\n\n_(HTML page — raw markup follows)_\n\n{page['content_html']}",
                media_type="text/markdown",
            )
        return PlainTextResponse(
            f"# {page['name']}\n\n{page['content_markdown'] or ''}",
            media_type="text/markdown",
        )
    return dict(page)


@router.get("/tables/{table_id}")
async def public_table(
    table_id: UUID,
    current_user: dict | None = Depends(get_current_user_optional),
):
    pool = get_pool()
    viewer = _viewer(current_user)
    if not await permission_service.check_access("table", table_id, viewer):
        raise HTTPException(status_code=404, detail="Table not found")

    t = await pool.fetchrow(
        "SELECT id, name, description, columns, workspace_id, updated_at FROM tables WHERE id = $1",
        table_id,
    )
    if not t:
        raise HTTPException(status_code=404, detail="Table not found")
    rows = await pool.fetch(
        "SELECT data, row_order FROM table_rows WHERE table_id = $1 "
        "ORDER BY row_order LIMIT 500",
        table_id,
    )
    return {
        "table": dict(t),
        "rows": [{"data": r["data"], "row_order": r["row_order"]} for r in rows],
    }


@router.get("/files/{file_id}")
async def public_file(
    file_id: UUID,
    current_user: dict | None = Depends(get_current_user_optional),
):
    pool = get_pool()
    viewer = _viewer(current_user)
    if not await permission_service.check_access("file", file_id, viewer):
        raise HTTPException(status_code=404, detail="File not found")

    f = await pool.fetchrow(
        "SELECT id, name, content_type, size_bytes, workspace_id, created_at FROM files WHERE id = $1",
        file_id,
    )
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return dict(f)
