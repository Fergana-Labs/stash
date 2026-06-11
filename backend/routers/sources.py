"""Connected-source registry endpoints.

A source is added per workspace and per user. It belongs to the member who
connects it (`owner_user_id = current_user`) inside that workspace, and only they
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
    permission_service,
    security_audit_service,
    source_service,
    task_service,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/sources", tags=["sources"])


async def _require_member(workspace_id: UUID, user_id: UUID) -> None:
    if await permission_service.get_workspace_role(workspace_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")


async def _require_write(workspace_id: UUID, user_id: UUID) -> None:
    role = await permission_service.get_workspace_role(workspace_id, user_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if role not in ("owner", "editor"):
        raise HTTPException(status_code=403, detail="Viewers can read but not manage sources")


async def _audit_source_action(
    *,
    action: str,
    workspace_id: UUID,
    user_id: UUID,
    source: str | None,
    metadata: dict | None = None,
) -> None:
    target_type = "source"
    target_id = source
    source_type = None
    provider = None

    if source is None:
        target_type = "source_collection"
        target_id = None
    elif source in (source_service.NATIVE_FILES, source_service.NATIVE_SESSIONS):
        source_type = source
    else:
        try:
            source_id = UUID(source)
        except ValueError:
            source_id = None
        connected = (
            await source_service.get_owned_source_in_workspace(source_id, user_id, workspace_id)
            if source_id
            else None
        )
        if connected:
            target_id = connected["id"]
            source_type = connected["source_type"]
            provider = source_service.SOURCE_TYPE_PROVIDER.get(source_type)

    await security_audit_service.record_event(
        action=action,
        actor_user_id=user_id,
        workspace_id=workspace_id,
        target_type=target_type,
        target_id=target_id,
        provider=provider,
        source_type=source_type,
        metadata=metadata,
    )


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


async def _resolve_snowflake_source(user_id) -> tuple[str, str]:
    """Snowflake is one connection per user; external_ref is the account.
    Confirm the credentials exist (raises 401 if not connected)."""
    import json

    creds = json.loads(await integration_storage.get_valid_token(user_id, "snowflake"))
    account = creds.get("account", "snowflake")
    return account, f"Snowflake ({account})"


@router.get("")
async def list_sources(workspace_id: UUID, current_user: dict = Depends(get_current_user)):
    """Sources this user can see here: native files + sessions, plus their own
    connected sources."""
    await _require_member(workspace_id, current_user["id"])
    return {"sources": await source_service.list_sources(workspace_id, current_user["id"])}


@router.get("/search")
async def search_sources(
    workspace_id: UUID,
    q: str,
    source: str | None = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Unified search. Omit `source` to search everything the user can see
    (files + sessions + their connected sources), or pass a handle to scope."""
    await _require_member(workspace_id, current_user["id"])
    results = await source_service.search_all(
        workspace_id, current_user["id"], q, source=source, limit=limit
    )
    if results is None:
        raise HTTPException(status_code=404, detail="Source not found")
    await _audit_source_action(
        action="source.searched",
        workspace_id=workspace_id,
        user_id=current_user["id"],
        source=source,
        metadata={
            "query_hash": security_audit_service.hash_value(q),
            "limit": limit,
            "result_count": len(results),
        },
    )
    return {"results": results}


@router.get("/{source}/entries")
async def list_source_entries(
    workspace_id: UUID,
    source: str,
    path: str = "",
    current_user: dict = Depends(get_current_user),
):
    """List a source's entries like a file system. `source` is 'files',
    'sessions', or a connected-source id; `path` scopes connected sources."""
    await _require_member(workspace_id, current_user["id"])
    entries = await source_service.source_entries(
        workspace_id, current_user["id"], source, prefix=path
    )
    if entries is None:
        raise HTTPException(status_code=404, detail="Source not found")
    await _audit_source_action(
        action="source.entries_listed",
        workspace_id=workspace_id,
        user_id=current_user["id"],
        source=source,
        metadata={
            "path_hash": security_audit_service.hash_value(path),
            "result_count": len(entries),
        },
    )
    return {"entries": entries}


@router.get("/{source}/doc")
async def read_source_doc(
    workspace_id: UUID,
    source: str,
    ref: str,
    current_user: dict = Depends(get_current_user),
):
    """Read one document. `ref` is a page id (files), a session id (sessions),
    or a document path (connected sources)."""
    await _require_member(workspace_id, current_user["id"])
    source_ok, doc = await source_service.source_document(
        workspace_id, current_user["id"], source, ref
    )
    if not source_ok:
        raise HTTPException(status_code=404, detail="Source not found")
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await _audit_source_action(
        action="source.document_read",
        workspace_id=workspace_id,
        user_id=current_user["id"],
        source=source,
        metadata={"ref_hash": security_audit_service.hash_value(ref)},
    )
    return doc


@router.get("/{source_id}/status")
async def source_status(
    workspace_id: UUID,
    source_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Sync/index status for one connected source (for the integration page):
    sync_status, last_synced_at, sync_error, and how many items are indexed."""
    await _require_member(workspace_id, current_user["id"])
    source = await source_service.get_owned_source_in_workspace(
        source_id,
        current_user["id"],
        workspace_id,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return {**source, "item_count": await source_service.source_item_count(source)}


class QuerySourceRequest(BaseModel):
    sql: str
    limit: int = 200


@router.post("/{source}/query")
async def query_source(
    workspace_id: UUID,
    source: str,
    body: QuerySourceRequest,
    current_user: dict = Depends(get_current_user),
):
    """Run a read-only SQL query against a queryable source (Snowflake)."""
    await _require_member(workspace_id, current_user["id"])
    result = await source_service.query_source(
        workspace_id, current_user["id"], source, body.sql, limit=body.limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    await _audit_source_action(
        action="source.queried",
        workspace_id=workspace_id,
        user_id=current_user["id"],
        source=source,
        metadata={
            "sql_hash": security_audit_service.hash_value(body.sql),
            "limit": body.limit,
            "row_count": result.get("row_count"),
            "error": bool(result.get("error")),
        },
    )
    return result


class FetchHistoryRequest(BaseModel):
    since: str  # ISO-8601 date/datetime
    until: str | None = None
    limit: int = 500


@router.post("/{source}/history")
async def fetch_source_history(
    workspace_id: UUID,
    source: str,
    body: FetchHistoryRequest,
    current_user: dict = Depends(get_current_user),
):
    """Pull older data for a time range from a copied source that supports it
    (Slack/Gong), caching it so it becomes searchable."""
    await _require_write(workspace_id, current_user["id"])
    result = await source_service.fetch_history(
        workspace_id, current_user["id"], source, body.since, until=body.until, limit=body.limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    await _audit_source_action(
        action="source.history_fetched",
        workspace_id=workspace_id,
        user_id=current_user["id"],
        source=source,
        metadata={
            "since_hash": security_audit_service.hash_value(body.since),
            "until_hash": security_audit_service.hash_value(body.until),
            "limit": body.limit,
            "fetched": result.get("fetched"),
            "error": bool(result.get("error")),
        },
    )
    return result


@router.post("")
async def add_source(
    workspace_id: UUID,
    body: AddSourceRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_write(workspace_id, current_user["id"])
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
    elif body.source_type == "snowflake" and not external_ref:
        external_ref, resolved_name = await _resolve_snowflake_source(current_user["id"])
        display_name = display_name or resolved_name

    if not external_ref:
        raise HTTPException(status_code=400, detail="external_ref is required")
    try:
        created = await source_service.create_source(
            workspace_id=workspace_id,
            owner_user_id=current_user["id"],
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
        workspace_id=workspace_id,
        target_type="source",
        target_id=created["id"],
        provider=source_service.SOURCE_TYPE_PROVIDER.get(created["source_type"]),
        source_type=created["source_type"],
        metadata={"capability": created["capability"]},
    )
    return created


@router.post("/{source_id}/sync")
async def sync_source_now(
    workspace_id: UUID,
    source_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Trigger an immediate re-index of an owned source."""
    await _require_write(workspace_id, current_user["id"])
    source = await source_service.get_owned_source_in_workspace(
        source_id,
        current_user["id"],
        workspace_id,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    task_id = str(uuid4())
    await task_service.register_task(
        task_id=task_id,
        user_id=current_user["id"],
        workspace_id=workspace_id,
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
        workspace_id=workspace_id,
        target_type="source",
        target_id=str(source_id),
        provider=source_service.SOURCE_TYPE_PROVIDER.get(source["source_type"]),
        source_type=source["source_type"],
        metadata={"task_id": task_id},
    )
    return {"task_id": task_id}


@router.delete("/{source_id}")
async def remove_source(
    workspace_id: UUID,
    source_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _require_write(workspace_id, current_user["id"])
    source = await source_service.get_owned_source_in_workspace(
        source_id,
        current_user["id"],
        workspace_id,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    deleted = await source_service.delete_source(source_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")
    await security_audit_service.record_event(
        action="source.deleted",
        actor_user_id=current_user["id"],
        workspace_id=workspace_id,
        target_type="source",
        target_id=str(source_id),
        provider=source_service.SOURCE_TYPE_PROVIDER.get(source["source_type"]),
        source_type=source["source_type"],
    )
    return {"deleted": True, "source_id": str(source_id)}
