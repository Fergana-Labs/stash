"""The hopper: drop anything, watch it become legible to your agent.

This service owns only the ledger (`hopper_items`) and the reserved Hopper
folder. The work of making a drop readable belongs to the pipelines that
already do it — files/pages ingest, url_imports — so status is read live off
those rows rather than mirrored here. See migration 0185.
"""

from uuid import UUID

from ..database import get_pool
from . import files_tree_service, url_import_service

FOLDER_NAME = "Hopper"

# Enough of the agent-visible text to prove the drop is readable, without
# shipping whole documents into a list response.
PREVIEW_CHARS = 400

# Every status the feed can report. `link_only` means we kept the URL but
# could not read the page; `needs_extension` means the site refused our
# server and only the browser extension can reach it; `no_text` means the
# file is stored but held nothing an agent can read.
STATUSES = ("reading", "legible", "no_text", "link_only", "needs_extension", "failed")


_FOLDER_SELECT = "SELECT id, name FROM folders WHERE owner_user_id = $1 AND parent_folder_id IS NULL AND name = $2"


async def find_folder(owner_user_id: UUID) -> dict | None:
    """The Hopper folder, if this owner has dropped anything yet. Reads never
    create it — an empty hopper has no folder to browse."""
    row = await get_pool().fetchrow(_FOLDER_SELECT, owner_user_id, FOLDER_NAME)
    return dict(row) if row else None


async def get_or_create_folder(owner_user_id: UUID, created_by: UUID) -> dict:
    """The one top-level folder every drop lands in, so `/Hopper` is a place
    the agent (and the user) can browse."""
    existing = await find_folder(owner_user_id)
    if existing:
        return existing
    try:
        folder = await files_tree_service.create_folder(owner_user_id, FOLDER_NAME, created_by)
    except files_tree_service.DuplicateFolderName:
        # Lost a race with a concurrent drop — the folder now exists.
        return await find_folder(owner_user_id)
    return {"id": folder["id"], "name": folder["name"]}


async def record(
    *,
    owner_user_id: UUID,
    created_by: UUID,
    kind: str,
    label: str,
    page_id: UUID | None = None,
    file_id: UUID | None = None,
    url_import_id: UUID | None = None,
) -> UUID:
    return await get_pool().fetchval(
        "INSERT INTO hopper_items "
        "  (owner_user_id, created_by, kind, label, page_id, file_id, url_import_id) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        owner_user_id,
        created_by,
        kind,
        label,
        page_id,
        file_id,
        url_import_id,
    )


# A drop points at its target either directly (files/notes) or through the
# import row that produced it (links) — never both, so picking the non-null
# one is a rename, not a fallback.
_SELECT = f"""
WITH item AS (
    SELECT h.id, h.kind, h.label, h.created_at,
           COALESCE(h.page_id, u.result_page_id) AS target_page_id,
           COALESCE(h.file_id, u.result_file_id) AS target_file_id,
           u.status AS import_status,
           u.error AS import_error,
           u.attempts AS import_attempts
    FROM hopper_items h
    LEFT JOIN url_imports u ON u.id = h.url_import_id
    WHERE h.owner_user_id = $1
)
SELECT i.*,
       p.name AS page_name,
       p.content_type AS page_content_type,
       left(p.content_markdown, {PREVIEW_CHARS}) AS page_preview,
       f.name AS file_name,
       f.extraction_status,
       f.extraction_error,
       left(f.extracted_text, {PREVIEW_CHARS}) AS file_preview
FROM item i
LEFT JOIN pages p ON p.id = i.target_page_id AND p.deleted_at IS NULL
LEFT JOIN files f ON f.id = i.target_file_id AND f.deleted_at IS NULL
"""


async def list_items(owner_user_id: UUID, limit: int) -> list[dict]:
    rows = await get_pool().fetch(
        _SELECT + " ORDER BY i.created_at DESC LIMIT $2", owner_user_id, limit
    )
    return [_to_item(r) for r in rows]


async def get_item(item_id: UUID, owner_user_id: UUID) -> dict | None:
    row = await get_pool().fetchrow(_SELECT + " WHERE i.id = $2", owner_user_id, item_id)
    return _to_item(row) if row else None


def _to_item(row) -> dict:
    status, detail = _legibility(row)
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "label": row["label"],
        "status": status,
        "detail": detail,
        "preview": _preview(row),
        "target": _target(row),
        "created_at": row["created_at"],
    }


def _target(row) -> dict | None:
    """Where the drop landed, once it has landed. Pending links have no
    target yet; a trashed target reads as gone (the join dropped it)."""
    if row["page_name"] is not None:
        return {"kind": "page", "id": str(row["target_page_id"]), "name": row["page_name"]}
    if row["file_name"] is not None:
        return {"kind": "file", "id": str(row["target_file_id"]), "name": row["file_name"]}
    return None


def _preview(row) -> str:
    """The first of what the agent reads. Pages hold their own text; a file's
    text only exists once extraction has run."""
    if row["page_name"] is not None:
        return row["page_preview"] if row["page_content_type"] == "markdown" else ""
    if row["file_name"] is not None:
        return row["file_preview"] or ""
    return ""


def _legibility(row) -> tuple[str, str]:
    """(status, detail) — the honest answer to "can my agent read this yet?"."""
    import_status = row["import_status"]
    if import_status is not None:
        stalled = _import_stalled(import_status, row["import_attempts"])
        if stalled is not None:
            return stalled
        # A finished import that kept only the link never produced content.
        if row["import_error"]:
            return "link_only", row["import_error"]

    if row["page_name"] is not None:
        return "legible", ""

    if row["file_name"] is not None:
        extraction = row["extraction_status"]
        if extraction == "done":
            # An empty preview after a finished extraction means the file
            # yielded no text at all — stored, but not readable.
            if row["file_preview"]:
                return "legible", ""
            return "no_text", "Stored, but nothing in it could be read as text"
        if extraction == "failed":
            return "failed", row["extraction_error"] or "Text extraction failed"
        return "reading", ""

    # No target and no import still running: the drop's target was deleted, or
    # an import reported success without content. Either way there is nothing
    # for the agent to read, and saying so beats showing a hopeful spinner.
    return "failed", "Nothing landed in your Stash for this drop"


def _import_stalled(status: str, attempts: int) -> tuple[str, str] | None:
    """Import states that are not yet a landed target. Returns None once the
    import is done and the target columns take over."""
    if status == "needs_client":
        return (
            "needs_extension",
            "This site blocks our servers — clip it with the browser extension",
        )
    if status == "failed" and attempts >= url_import_service.MAX_ATTEMPTS:
        return "failed", "Could not fetch this link"
    if status in ("pending", "processing", "failed"):
        return "reading", ""
    return None
