"""Connected-source registry endpoints.

A source is added per scope and per user. It belongs to the member who
connects it (`owner_user_id = current_user`) inside that scope, and only they
can list, read, or remove it there. The agent reaches a source's indexed content
through the source tools; these endpoints just manage the registry. Indexing
(sync tasks) is wired per source type in later phases.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..celery_app import celery
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
    if not await user_scope_service.is_owner(owner_user_id, user_id):
        raise HTTPException(status_code=404, detail="Scope not found")


async def _require_write(owner_user_id: UUID, user_id: UUID) -> None:
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
    return me["id"], f"Twitter / X (@{username})"


async def _resolve_linear_source(user_id) -> tuple[str, str]:
    """A Linear source covers every issue the connected user can read, so there
    is one canonical ref ('me'). Confirm the token exists (raises 401 if not
    connected) before creating the source."""
    await integration_storage.get_valid_token(user_id, "linear")
    return "me", "Linear"


@router.get("")
async def list_sources(current_user: dict = Depends(get_current_user)):
    """Sources this user can see here: native files + sessions, plus their own
    connected sources."""
    owner_user_id = current_user["id"]
    await _require_member(owner_user_id, current_user["id"])
    return {"sources": await source_service.list_sources(owner_user_id, current_user["id"])}


@router.get("/search")
async def search_sources(
    q: str,
    source: str | None = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Unified search. Omit `source` to search everything the user can see
    (files + sessions + their connected sources), or pass a handle to scope."""
    owner_user_id = current_user["id"]
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
):
    """The whole scope as one filesystem: every source the user can see,
    each with a nested entry tree trimmed to `depth` levels."""
    owner_user_id = current_user["id"]
    await _require_member(owner_user_id, current_user["id"])
    return {
        "sources": await source_service.sources_tree(owner_user_id, current_user["id"], depth=depth)
    }


@router.get("/{source}/entries")
async def list_source_entries(
    source: str,
    path: str = "",
    current_user: dict = Depends(get_current_user),
):
    """List a source's entries like a file system. `source` is 'files',
    'sessions', or a connected-source id; `path` scopes connected sources."""
    owner_user_id = current_user["id"]
    await _require_member(owner_user_id, current_user["id"])
    entries = await source_service.source_entries(
        owner_user_id, current_user["id"], source, prefix=path
    )
    if entries is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"entries": entries}


@router.get("/{source}/doc")
async def read_source_doc(
    source: str,
    ref: str,
    current_user: dict = Depends(get_current_user),
):
    """Read one document. `ref` is a page id (files), a session id (sessions),
    or a document path (connected sources)."""
    owner_user_id = current_user["id"]
    await _require_member(owner_user_id, current_user["id"])
    source_ok, doc = await source_service.source_document(
        owner_user_id, current_user["id"], source, ref
    )
    if not source_ok:
        raise HTTPException(status_code=404, detail="Source not found")
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
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
):
    owner_user_id = current_user["id"]
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
        external_ref, resolved_name = await _resolve_twitter_source(current_user["id"])
        display_name = resolved_name
    elif body.source_type == "linear":
        external_ref, resolved_name = await _resolve_linear_source(current_user["id"])
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
