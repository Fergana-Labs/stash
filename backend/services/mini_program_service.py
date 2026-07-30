"""Mini programs: table manifests that the UI renders as an app.

A mini program is a table plus a manifest describing how to fill and present
it: the column schema, which columns an LLM derives (`enrichment`), the views
to seed, and which columns carry the title/body/labels of a row so the client
can render cards and a detail pane without knowing what a bookmark is.

Manifests reference columns **by name**. Column ids are server-generated at
create time, so `resolve` maps names to ids once the table exists; nothing
downstream hardcodes a `col_*`.

To add a mini program, append a manifest to MANIFESTS. To retire one, delete
it — the table stays as an ordinary table, which is what the UI falls back to
when `mini_program` names a manifest that no longer exists.
"""

from __future__ import annotations

from uuid import UUID

from asyncpg.exceptions import UniqueViolationError

from ..database import get_pool
from . import files_tree_service, table_service

BOOKMARKS_SLUG = "bookmarks"

# Kinds an enrichment target can ask for. The worker owns one prompt per kind.
KIND_SUMMARY = "summary"
KIND_LABELS = "labels"


BOOKMARKS_MANIFEST = {
    "slug": BOOKMARKS_SLUG,
    "title": "Bookmarks",
    "tagline": "Everything you save, summarised and sorted by topic.",
    "icon": "bookmark",
    "folder": "Clips",
    "table_name": "Bookmarks",
    "description": "Everything you've saved with the Stash browser extension.",
    # Published skills that read this table. Named, not slugged: slugs carry a
    # random suffix minted at publish time, so the manifest would go stale the
    # first time a skill was republished. Resolved against the service account
    # at read time — a name nobody has published yet simply doesn't appear.
    "skills": ["brief", "resurface", "overview", "cleanup"],
    "empty_state": {
        "title": "Save your first bookmark",
        "description": (
            "Use the Stash browser extension to save a page, PDF, video, or post. "
            "It will appear here and be summarised automatically."
        ),
        "action": {"label": "Learn how to save with Stash", "href": "/extension"},
    },
    "columns": [
        {"name": "Title", "type": "text"},
        {"name": "URL", "type": "url"},
        {
            "name": "Type",
            "type": "select",
            "options": ["Page", "PDF", "Video", "Tweet", "Instagram", "Link"],
        },
        {"name": "Saved", "type": "text"},
        {"name": "Site", "type": "text"},
        {"name": "Clip", "type": "url"},
        {"name": "Summary", "type": "text", "width": 320},
        {"name": "Topics", "type": "multiselect", "options": []},
        # Written by the link checker; the "Broken" filter reads it. Kept as a
        # column rather than hidden state so it's visible and correctable in
        # the grid when a check is wrong (a 403 behind Cloudflare, say).
        {"name": "Status", "type": "select", "options": ["OK", "Broken"], "width": 100},
    ],
    "enrichment": {
        # Title/URL/Site give the model context cheaply; the real text comes
        # from the clipped page that "Clip" points at.
        "context_columns": ["Title", "Site", "URL"],
        "page_column": "Clip",
        "targets": [
            {
                "column": "Summary",
                "kind": KIND_SUMMARY,
                "instruction": (
                    "Two sentences: what this is, and why someone who saved it "
                    "would come back to it. No preamble, no 'This article'."
                ),
            },
            # Two labels, not four. Four over-generates: each extra slot the
            # model has to fill is one it fills with a near-synonym of a label
            # it already used, which is what turns topic chips into noise.
            {"column": "Topics", "kind": KIND_LABELS, "max": 2},
        ],
    },
    "views": [
        {"name": "Recent", "layout": "cards", "sort_by": "Saved", "sort_order": "desc"},
        {"name": "By topic", "layout": "cards", "sort_by": "Topics", "sort_order": "asc"},
        {"name": "All rows", "layout": "table"},
    ],
    # How the client renders one row as a card and as a detail pane.
    "detail": {
        "title": "Title",
        "subtitle": "Site",
        "body": "Summary",
        "labels": "Topics",
        "link": "URL",
        "content": "Clip",
        "badge": "Type",
        "timestamp": "Saved",
        "status": "Status",
    },
}


MANIFESTS = [BOOKMARKS_MANIFEST]


def list_manifests() -> list[dict]:
    return MANIFESTS


def get_manifest(slug: str) -> dict | None:
    return next((m for m in MANIFESTS if m["slug"] == slug), None)


def column_ids(manifest: dict, columns: list[dict]) -> dict[str, str]:
    """Map manifest column names to the table's generated column ids."""
    by_name = {c["name"]: c["id"] for c in columns}
    return {
        name: by_name[name] for name in (c["name"] for c in manifest["columns"]) if name in by_name
    }


def resolve(manifest: dict, columns: list[dict]) -> dict:
    """The manifest with every column name swapped for its column id, so the
    client can address cells directly. Names that aren't on the table (an
    older table that predates a manifest column) are dropped."""
    ids = column_ids(manifest, columns)
    detail = {slot: ids[name] for slot, name in manifest["detail"].items() if name in ids}
    return {
        "slug": manifest["slug"],
        "title": manifest["title"],
        "tagline": manifest["tagline"],
        "icon": manifest["icon"],
        "empty_state": manifest["empty_state"],
        "detail": detail,
        "enriched_columns": [
            ids[t["column"]] for t in manifest["enrichment"]["targets"] if t["column"] in ids
        ],
    }


def _enrichment_config(manifest: dict, columns: list[dict]) -> dict:
    ids = column_ids(manifest, columns)
    spec = manifest["enrichment"]
    return {
        "enabled": True,
        "context_columns": [ids[n] for n in spec["context_columns"] if n in ids],
        "page_column": ids.get(spec["page_column"]),
        "targets": [
            {**t, "column": ids[t["column"]]} for t in spec["targets"] if t["column"] in ids
        ],
    }


def _seed_views(manifest: dict, columns: list[dict]) -> list[dict]:
    ids = column_ids(manifest, columns)
    views = []
    for i, view in enumerate(manifest["views"]):
        seeded = {"id": f"view_seed_{i}", "name": view["name"], "layout": view["layout"]}
        if view.get("sort_by") in ids:
            seeded["sort_by"] = ids[view["sort_by"]]
            seeded["sort_order"] = view.get("sort_order", "desc")
        views.append(seeded)
    return views


async def find_table(slug: str, owner_user_id: UUID) -> dict | None:
    """The owner's table for this mini program, or None if they have none yet."""
    row = await get_pool().fetchval(
        "SELECT id FROM tables WHERE owner_user_id = $1 AND mini_program = $2",
        owner_user_id,
        slug,
    )
    return await table_service.get_table(row) if row else None


async def ensure_table(slug: str, owner_user_id: UUID, user_id: UUID) -> dict:
    """Get-or-create this owner's table for the mini program, seeded with the
    manifest's columns, views, and enrichment config.

    The unique index on (owner_user_id, mini_program) is what makes this
    race-safe across processes — a lost race raises, and we re-read the winner.
    """
    manifest = get_manifest(slug)
    if manifest is None:
        raise ValueError(f"Unknown mini program: {slug}")

    existing = await find_table(slug, owner_user_id)
    if existing:
        return existing

    # The app's folder is structural — the manifest resolves it by name, so it
    # is protected for the same reason Clips is.
    folder = await files_tree_service.find_or_create_root_folder(
        owner_user_id, manifest["folder"], user_id, protected=True
    )
    try:
        table = await table_service.create_table(
            owner_user_id,
            manifest["table_name"],
            manifest["description"],
            [dict(c) for c in manifest["columns"]],
            user_id,
            folder_id=folder["id"],
            mini_program=slug,
        )
    except UniqueViolationError:
        # A concurrent save won the index; its table is the one we want.
        winner = await find_table(slug, owner_user_id)
        if winner is None:
            raise
        return winner

    await _adopt(table, manifest)
    return await table_service.get_table(table["id"])


async def _adopt(table: dict, manifest: dict) -> None:
    """Fill in the parts of the manifest that can't go in the INSERT: the
    enrichment config, the seeded views, and row embeddings so search covers
    it. The slug itself is stamped at insert time, for the unique index."""
    columns = table["columns"]
    await get_pool().execute(
        "UPDATE tables SET enrichment_config = $1, views = $2 WHERE id = $3",
        _enrichment_config(manifest, columns),
        _seed_views(manifest, columns),
        table["id"],
    )
    ids = column_ids(manifest, columns)
    embed_columns = [ids[n] for n in ("Title", "Summary", "Topics", "Site") if n in ids]
    await table_service.set_embedding_config(
        table["id"], {"enabled": True, "columns": embed_columns}, table["created_by"]
    )
