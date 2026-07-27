"""Mini programs: app-shaped tables (Bookmarks today, more later).

The client needs two things the generic tables API can't give it: a stable
slug that resolves to *this user's* table for an app, and the manifest that
says which column is the title, the body, the labels — so it can render cards
and a detail pane without knowing what a bookmark is.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services import mini_program_query, mini_program_service, table_service

router = APIRouter(prefix="/api/v1/me/apps", tags=["mini-programs"])

MAX_PAGE = 200
MAX_BULK_ROWS = 500


async def _resolve(slug: str, user_id) -> tuple[dict, dict]:
    """The caller's table for this app plus its resolved manifest. Every row
    operation goes through here, so a row id from someone else's table is
    unreachable — the table id is never taken from the request."""
    manifest = mini_program_service.get_manifest(slug)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"No mini program named {slug!r}")
    table = await mini_program_service.find_table(slug, user_id)
    if table is None:
        raise HTTPException(status_code=404, detail=f"{manifest['title']} is not set up yet")
    return table, mini_program_service.resolve(manifest, table["columns"])


def _card(manifest: dict, table: dict | None) -> dict:
    return {
        "slug": manifest["slug"],
        "title": manifest["title"],
        "tagline": manifest["tagline"],
        "icon": manifest["icon"],
        "installed": table is not None,
        "table_id": str(table["id"]) if table else None,
        "row_count": table.get("row_count") if table else 0,
    }


@router.get("")
async def list_apps(current_user: dict = Depends(get_current_user)):
    """Every mini program, flagged with whether this user has one yet. Drives
    the app gallery — installed apps first, the rest as templates."""
    apps = []
    for manifest in mini_program_service.list_manifests():
        table = await mini_program_service.find_table(manifest["slug"], current_user["id"])
        apps.append(_card(manifest, table))
    return {"apps": apps}


@router.get("/{slug}")
async def get_app(slug: str, current_user: dict = Depends(get_current_user)):
    """Resolve a slug to this user's table plus the column-id-resolved
    manifest. 404 when they haven't installed it — the client offers to."""
    manifest = mini_program_service.get_manifest(slug)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"No mini program named {slug!r}")
    table = await mini_program_service.find_table(slug, current_user["id"])
    if table is None:
        raise HTTPException(status_code=404, detail=f"{manifest['title']} is not set up yet")
    return {
        "table_id": str(table["id"]),
        "row_count": table["row_count"],
        "manifest": mini_program_service.resolve(manifest, table["columns"]),
    }


@router.post("/{slug}", status_code=201)
async def install_app(slug: str, current_user: dict = Depends(get_current_user)):
    """Create this user's table for a mini program, seeded from the manifest.
    Idempotent — installing twice returns the existing table."""
    if mini_program_service.get_manifest(slug) is None:
        raise HTTPException(status_code=404, detail=f"No mini program named {slug!r}")
    table = await mini_program_service.ensure_table(slug, current_user["id"], current_user["id"])
    manifest = mini_program_service.get_manifest(slug)
    return {
        "table_id": str(table["id"]),
        "row_count": table["row_count"],
        "manifest": mini_program_service.resolve(manifest, table["columns"]),
    }


@router.post("/{slug}/rows/{row_id}/reenrich")
async def reenrich_row(
    slug: str,
    row_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Queue one row for re-enrichment — the detail pane's "regenerate".
    Clears the hash so the sweep doesn't skip it as unchanged."""
    table = await mini_program_service.find_table(slug, current_user["id"])
    if table is None:
        raise HTTPException(status_code=404, detail="App is not set up yet")
    updated = await table_service.mark_row_enrich_stale(table["id"], row_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Row not found")
    return {"status": "queued"}


# ===== Rows: paging, filters, facets =====


@router.get("/{slug}/rows")
async def list_rows(
    slug: str,
    q: str = "",
    topic: str | None = None,
    filter: str | None = Query(None, description="duplicates | untagged | broken"),
    limit: int = Query(60, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Filtered, paged rows. Filtering and search run over the whole table:
    doing them client-side over a loaded page meant a large library silently
    searched only its first page."""
    table, manifest = await _resolve(slug, current_user["id"])
    return await mini_program_query.query_rows(
        table["id"],
        manifest["detail"],
        q=q,
        topic=topic,
        filter_=filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{slug}/facets")
async def get_facets(slug: str, current_user: dict = Depends(get_current_user)):
    """Counts for every filter chip, over the whole table — topics, plus the
    derived duplicates / untagged / broken counts."""
    table, manifest = await _resolve(slug, current_user["id"])
    return await mini_program_query.facets(table["id"], manifest["detail"])


# ===== Editing =====


class TopicsRequest(BaseModel):
    topics: list[str] = Field(default_factory=list, max_length=20)


@router.put("/{slug}/rows/{row_id}/topics")
async def set_row_topics(
    slug: str,
    row_id: UUID,
    body: TopicsRequest,
    current_user: dict = Depends(get_current_user),
):
    """Replace one row's topics. New labels join the column's vocabulary so
    they're offered to the model and appear as filter chips."""
    table, manifest = await _resolve(slug, current_user["id"])
    label_col = manifest["detail"].get("labels")
    if not label_col:
        raise HTTPException(status_code=400, detail="This app has no topics column")

    topics = [t.strip() for t in body.topics if t.strip()]
    if not await mini_program_query.set_topics(table["id"], row_id, label_col, topics):
        raise HTTPException(status_code=404, detail="Row not found")
    await table_service.merge_column_options(table["id"], label_col, topics)
    return {"topics": topics}


class BulkRequest(BaseModel):
    row_ids: list[UUID] = Field(..., min_length=1, max_length=MAX_BULK_ROWS)
    action: str = Field(..., pattern="^(add_topics|remove_topic|delete)$")
    topics: list[str] = Field(default_factory=list, max_length=20)


@router.post("/{slug}/rows/bulk")
async def bulk_edit(
    slug: str,
    body: BulkRequest,
    current_user: dict = Depends(get_current_user),
):
    """Tag or delete many rows at once. Adding topics unions rather than
    replaces, so a bulk tag never discards labels the rows already carry."""
    table, manifest = await _resolve(slug, current_user["id"])
    label_col = manifest["detail"].get("labels")

    if body.action == "delete":
        return {"affected": await mini_program_query.bulk_delete(table["id"], body.row_ids)}

    if not label_col:
        raise HTTPException(status_code=400, detail="This app has no topics column")
    topics = [t.strip() for t in body.topics if t.strip()]
    if not topics:
        raise HTTPException(status_code=422, detail="No topics given")

    if body.action == "add_topics":
        affected = await mini_program_query.bulk_add_topics(
            table["id"], body.row_ids, label_col, topics
        )
        await table_service.merge_column_options(table["id"], label_col, topics)
    else:
        affected = await mini_program_query.bulk_remove_topic(
            table["id"], body.row_ids, label_col, topics[0]
        )
    return {"affected": affected}
