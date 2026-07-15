"""Connected-source registry endpoints.

A source belongs to the scope that connected it (`owner_user_id`). Reads run
in the active scope (the X-Stash-Scope header): a workspace member browsing
the workspace sees the workspace's connections — the org Drive hopper — while
personal scope shows their own. Mutations (connect, sync, remove, history)
stay owner-only: members read the hopper, only the scope owner wires it up.
The agent reaches a source's indexed content through the source tools; these
endpoints just manage the registry.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, get_scope
from ..celery_app import celery
from ..database import get_pool
from ..integrations import storage as integration_storage
from ..integrations.registry import get_provider
from ..services import (
    security_audit_service,
    source_service,
    task_service,
    user_scope_service,
)

router = APIRouter(prefix="/api/v1/me/sources", tags=["sources"])


async def _require_member(owner_user_id: UUID, user_id: UUID) -> None:
    """Read gate: the scope owner, or a member of the workspace it belongs to."""
    if not await user_scope_service.can_read(owner_user_id, user_id):
        raise HTTPException(status_code=404, detail="Scope not found")


async def _require_write(owner_user_id: UUID, user_id: UUID) -> None:
    """Mutation gate: owner only — members never manage the scope's sources."""
    if not await user_scope_service.is_owner(owner_user_id, user_id):
        raise HTTPException(status_code=404, detail="Scope not found")


class AddSourceRequest(BaseModel):
    source_type: str
    # Optional for sources where the connected account resolves the target. For
    # Gmail, pass the account email when more than one mailbox is connected.
    external_ref: str | None = None
    display_name: str | None = None
    settings: dict | None = None


async def _resolve_slack_source(user_id) -> tuple[str, str]:
    """Slack source external_ref = team id, display_name = team name, both from
    the connected user token."""
    token = await integration_storage.get_valid_token(user_id, "slack")
    info = await get_provider("slack").team_info(token)
    return info["team_id"], info["team_name"]


async def _resolve_granola_source(user_id) -> tuple[str, str]:
    """Granola is one connection per user, so the external_ref is a constant.
    Use Granola's MCP OAuth token path because it refreshes with the stored
    Dynamic Client Registration info."""
    from ..integrations.granola.oauth import get_valid_access_token

    await get_valid_access_token(user_id)
    return "granola", "Granola"


async def _resolve_gmail_source(user_id, account_key: str | None) -> tuple[str, str]:
    """Gmail source external_ref = the connected mailbox email."""
    status = await integration_storage.status(user_id, "gmail")
    accounts = status.get("accounts", [])
    if not accounts:
        raise HTTPException(status_code=401, detail="not connected to gmail")

    if not account_key:
        if len(accounts) != 1:
            raise HTTPException(status_code=400, detail="Choose a Gmail account to add.")
        account = accounts[0]
    else:
        key = account_key.strip().lower()
        account = next(
            (
                a
                for a in accounts
                if a["account_key"] == key or (a.get("account_email") or "").lower() == key
            ),
            None,
        )
        if account is None:
            raise HTTPException(status_code=400, detail="Gmail account is not connected.")

    email = account.get("account_email") or account["account_key"]
    await integration_storage.get_valid_token(user_id, "gmail", account["account_key"])
    return account["account_key"], f"Gmail ({email})"


async def _resolve_gong_source(user_id) -> tuple[str, str]:
    """Gong is one connection per user (all calls); external_ref is constant.
    Confirm the credentials exist (raises 401 if not connected)."""
    await integration_storage.get_valid_token(user_id, "gong")
    return "calls", "Gong"


async def _resolve_twitter_source(user_id) -> tuple[str, str]:
    """Twitter source external_ref is the connected X account's numeric user
    id, resolved once here so reads never depend on /users/me (X's most
    rate-limited endpoint). Caller-supplied refs are ignored — there are no
    saved-query sources (they would burn the owner's X quota on a schedule)."""
    from ..integrations.twitter.indexer import fetch_me

    token = await integration_storage.get_valid_token(user_id, "twitter")
    me = await fetch_me(token)
    username = me.get("username")
    if not username:
        raise HTTPException(
            status_code=400,
            detail="Reconnect Twitter / X before adding it as a source.",
        )
    return me["id"], username


async def _resolve_linear_source(user_id) -> tuple[str, str]:
    """A Linear source covers every issue the connected user can read, so there
    is one canonical ref ('me'). Confirm the token exists (raises 401 if not
    connected) before creating the source."""
    await integration_storage.get_valid_token(user_id, "linear")
    return "me", "Linear"


async def _resolve_posthog_source(user_id) -> tuple[str, str]:
    """One connected PostHog credential bundle represents one project."""
    await integration_storage.get_valid_token(user_id, "posthog")
    status = await integration_storage.status(user_id, "posthog")
    display_name = status.get("account_display_name")
    if not display_name:
        raise HTTPException(status_code=409, detail="Reconnect PostHog before adding it.")
    return "project", f"PostHog ({display_name})"


@router.get("")
async def list_sources(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Sources in the active scope's view: native files + sessions, plus the
    scope's connected sources."""
    owner_user_id = scope_user_id
    await _require_member(owner_user_id, current_user["id"])
    return {"sources": await source_service.list_sources(owner_user_id, current_user["id"])}


@router.get("/search")
async def search_sources(
    q: str,
    source: str | None = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Unified search. Omit `source` to search everything in the active scope
    (files + sessions + its connected sources), or pass a handle to scope."""
    owner_user_id = scope_user_id
    await _require_member(owner_user_id, current_user["id"])
    results = await source_service.search_all(
        owner_user_id, current_user["id"], q, source=source, limit=limit
    )
    if results is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"results": results}


@router.get("/tree")
async def sources_tree(
    depth: int = 3,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """The whole active scope as one filesystem: every source in its view,
    each with a nested entry tree trimmed to `depth` levels."""
    owner_user_id = scope_user_id
    await _require_member(owner_user_id, current_user["id"])
    return {
        "sources": await source_service.sources_tree(owner_user_id, current_user["id"], depth=depth)
    }


@router.get("/{source}/entries")
async def list_source_entries(
    source: str,
    path: str = "",
    limit: int = source_service.ENTRIES_LIMIT,
    after: str = "",
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """List a source's entries like a file system. `source` is 'files',
    'sessions', or a connected-source id; `path` scopes connected sources.
    `limit` caps the rows returned; callers detect truncation by requesting one
    extra row and checking whether it comes back. `after` is a keyset cursor
    (the last path of the previous page) for paging through big sources."""
    owner_user_id = scope_user_id
    await _require_member(owner_user_id, current_user["id"])
    entries = await source_service.source_entries(
        owner_user_id, current_user["id"], source, prefix=path, limit=limit, after=after
    )
    if entries is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"entries": entries}


@router.get("/{source}/doc")
async def read_source_doc(
    source: str,
    ref: str,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Read one document. `ref` is a page id (files), a session id (sessions),
    or a document path (connected sources)."""
    owner_user_id = scope_user_id
    await _require_member(owner_user_id, current_user["id"])
    source_ok, doc = await source_service.source_document(
        owner_user_id, current_user["id"], source, ref
    )
    if not source_ok:
        raise HTTPException(status_code=404, detail="Source not found")
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    # A document we cannot read is an error, not an empty document. The VFS turns
    # this into a per-file warning on stderr, so a `grep` reports what it skipped
    # instead of quietly reporting no matches.
    if "http_status" in doc:
        raise HTTPException(status_code=doc["http_status"], detail=doc["error"])
    return doc


@router.get("/{source_id}/status")
async def source_status(
    source_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Sync/index status for one connected source (for the integration page):
    sync_status, last_synced_at, sync_error, and how many items are indexed."""
    owner_user_id = current_user["id"]
    await _require_member(owner_user_id, current_user["id"])
    source = await source_service.get_owned_source(
        source_id,
        current_user["id"],
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return {**source, "item_count": await source_service.source_item_count(source)}


class FetchHistoryRequest(BaseModel):
    since: str  # ISO-8601 date/datetime
    until: str | None = None
    limit: int = 500


@router.post("/{source}/history")
async def fetch_source_history(
    source: str,
    body: FetchHistoryRequest,
    current_user: dict = Depends(get_current_user),
):
    """Pull older data for a time range from a copied source that supports it
    (Slack/Gong), caching it so it becomes searchable."""
    owner_user_id = current_user["id"]
    await _require_write(owner_user_id, current_user["id"])
    result = await source_service.fetch_history(
        owner_user_id, current_user["id"], source, body.since, until=body.until, limit=body.limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return result


@router.post("")
async def add_source(
    body: AddSourceRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    # Honors the scope header so a member's connect attempt in workspace mode
    # fails loud (owner-only) instead of silently landing in their personal
    # scope. Connecting as the workspace itself goes through its own API key.
    owner_user_id = scope_user_id
    await _require_write(owner_user_id, current_user["id"])
    if body.source_type not in source_service.SOURCE_CAPABILITY:
        raise HTTPException(status_code=400, detail=f"unknown source type: {body.source_type}")
    try:
        source_settings = source_service.normalize_source_settings(body.source_type, body.settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    external_ref = body.external_ref
    display_name = body.display_name
    if body.source_type == "slack" and not external_ref:
        external_ref, resolved_name = await _resolve_slack_source(current_user["id"])
        display_name = display_name or resolved_name
    elif body.source_type == "granola" and not external_ref:
        external_ref, resolved_name = await _resolve_granola_source(current_user["id"])
        display_name = display_name or resolved_name
    elif body.source_type == "gmail":
        external_ref, resolved_name = await _resolve_gmail_source(current_user["id"], external_ref)
        display_name = display_name or resolved_name
    elif body.source_type == "gong_calls" and not external_ref:
        external_ref, resolved_name = await _resolve_gong_source(current_user["id"])
        display_name = display_name or resolved_name
    elif body.source_type == "twitter":
        external_ref, username = await _resolve_twitter_source(current_user["id"])
        display_name = f"Twitter / X (@{username})"
    elif body.source_type == "twitter_bookmarks":
        external_ref, username = await _resolve_twitter_source(current_user["id"])
        display_name = f"X bookmarks (@{username})"
    elif body.source_type == "linear":
        external_ref, resolved_name = await _resolve_linear_source(current_user["id"])
        display_name = display_name or resolved_name
    elif body.source_type == "posthog_project":
        external_ref, resolved_name = await _resolve_posthog_source(current_user["id"])
        display_name = display_name or resolved_name

    if not external_ref:
        raise HTTPException(status_code=400, detail="external_ref is required")
    try:
        created = await source_service.create_source(
            owner_user_id=owner_user_id,
            source_type=body.source_type,
            external_ref=external_ref,
            display_name=display_name or external_ref,
            settings=source_settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await security_audit_service.record_event(
        action="source.created",
        actor_user_id=current_user["id"],
        owner_user_id=owner_user_id,
        target_type="source",
        target_id=created["id"],
        provider=source_service.SOURCE_TYPE_PROVIDER.get(created["source_type"]),
        source_type=created["source_type"],
        metadata={"capability": created["capability"]},
    )
    return created


@router.post("/{source_id}/sync")
async def sync_source_now(
    source_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Trigger an immediate re-index of an owned source."""
    owner_user_id = current_user["id"]
    await _require_write(owner_user_id, current_user["id"])
    source = await source_service.get_owned_source(
        source_id,
        current_user["id"],
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if source["source_type"] not in source_service.DEFAULT_SYNC_INTERVAL_S:
        # Search-driven sources have no indexer; the queued task would no-op,
        # so a 200 here would be a lie.
        raise HTTPException(status_code=400, detail="This source type does not sync")
    task_id = str(uuid4())
    await task_service.register_task(
        task_id=task_id,
        user_id=current_user["id"],
        owner_user_id=owner_user_id,
        task_type="source_sync",
        object_type="source",
        object_id=source_id,
    )
    # Mark syncing at enqueue (not just when the worker picks it up) so the UI
    # sees the in-flight sync as soon as this request returns.
    await source_service.mark_sync_started(source_id)
    celery.send_task(
        "backend.tasks.sources.sync_source",
        kwargs={"source_id": str(source_id)},
        task_id=task_id,
    )
    await security_audit_service.record_event(
        action="source.sync_requested",
        actor_user_id=current_user["id"],
        owner_user_id=owner_user_id,
        target_type="source",
        target_id=str(source_id),
        provider=source_service.SOURCE_TYPE_PROVIDER.get(source["source_type"]),
        source_type=source["source_type"],
        metadata={"task_id": task_id},
    )
    return {"task_id": task_id}


@router.delete("/{source_id}")
async def remove_source(
    source_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _require_write(owner_user_id, current_user["id"])
    source = await source_service.get_owned_source(
        source_id,
        current_user["id"],
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    deleted = await source_service.delete_source(source_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")
    await security_audit_service.record_event(
        action="source.deleted",
        actor_user_id=current_user["id"],
        owner_user_id=owner_user_id,
        target_type="source",
        target_id=str(source_id),
        provider=source_service.SOURCE_TYPE_PROVIDER.get(source["source_type"]),
        source_type=source["source_type"],
    )
    return {"deleted": True, "source_id": str(source_id)}


# ===== Saved-items push (browser extension) =====

saved_items_router = APIRouter(prefix="/api/v1/me/saved-items", tags=["sources"])

_IG_SHORTCODE_RE = re.compile(r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")
MAX_SAVED_ITEMS_PER_PUSH = 500


class SavedItem(BaseModel):
    url: str
    saved_at: datetime | None = None


class SavedItemsPush(BaseModel):
    platform: Literal["instagram"]
    items: list[SavedItem]


@saved_items_router.post("")
async def push_saved_items(
    body: SavedItemsPush,
    current_user: dict = Depends(get_current_user),
):
    """The extension pushes the user's saved-post URLs. Get-or-creates the
    instagram_saves source (no setup ordering between connector card and
    extension), inserts pending skeleton rows, and kicks a sync so
    hydration starts immediately."""
    owner_user_id = current_user["id"]
    if not body.items:
        raise HTTPException(status_code=400, detail="No items given")
    if len(body.items) > MAX_SAVED_ITEMS_PER_PUSH:
        raise HTTPException(
            status_code=413,
            detail=f"Too many items ({len(body.items)}, max {MAX_SAVED_ITEMS_PER_PUSH})",
        )

    parsed: list[tuple[str, SavedItem]] = []
    for item in body.items:
        match = _IG_SHORTCODE_RE.search(item.url)
        if not match:
            raise HTTPException(status_code=400, detail=f"Not an Instagram post URL: {item.url}")
        parsed.append((match.group(1), item))

    source = await source_service.create_source(
        owner_user_id=owner_user_id,
        source_type="instagram_saves",
        external_ref="saves",
        display_name="Instagram saves",
        settings={},
    )
    source_id = UUID(source["id"])

    pool = get_pool()
    new = 0
    for shortcode, item in parsed:
        inserted = await pool.fetchval(
            "INSERT INTO instagram_save_docs "
            "(owner_user_id, source_id, path, name, kind, external_ref, saved_at) "
            "VALUES ($1, $2, $3, $3, 'post', $3, $4) "
            "ON CONFLICT (source_id, path) DO NOTHING RETURNING 1",
            owner_user_id,
            source_id,
            shortcode,
            item.saved_at,
        )
        if inserted:
            new += 1

    if new:
        celery.send_task("backend.tasks.sources.sync_source", args=[str(source_id)])
    return {"accepted": len(parsed), "new": new, "existing": len(parsed) - new}
