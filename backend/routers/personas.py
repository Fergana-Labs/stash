from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import get_current_user
from ..models import (
    PersonaCreateRequest, PersonaPageCreateRequest, PersonaPageUpdateRequest,
    PersonaProfile, PersonaResponse, PersonaUpdateRequest,
    HistoryEventBatchRequest, HistoryEventCreateRequest,
    HistoryEventListResponse, HistoryEventResponse, HistoryResponse,
    InjectionRequest, InjectionResponse,
    NotebookResponse, PageResponse, SyncManifestResponse,
    UnreadChatResponse, UnreadListResponse, WatchListResponse, WatchResponse,
)
from ..services import persona_identity_service, injection_service, memory_service, notebook_service, sleep_service, watch_service

router = APIRouter(prefix="/api/v1/personas", tags=["personas"])


def _require_human(user: dict) -> None:
    if user["type"] != "human":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only human users can manage persona identities",
        )


@router.post("", response_model=PersonaResponse, status_code=201)
async def create_persona(
    req: PersonaCreateRequest, current_user: dict = Depends(get_current_user)
):
    _require_human(current_user)
    try:
        persona, api_key = await persona_identity_service.create_persona(
            owner_id=current_user["id"],
            name=req.name,
            display_name=req.display_name,
            description=req.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return PersonaResponse(**persona, api_key=api_key)


@router.get("", response_model=list[PersonaProfile])
async def list_personas(current_user: dict = Depends(get_current_user)):
    _require_human(current_user)
    personas = await persona_identity_service.list_owner_personas(current_user["id"])
    return [PersonaProfile(**p) for p in personas]


@router.get("/{persona_id}", response_model=PersonaProfile)
async def get_persona(persona_id: UUID, current_user: dict = Depends(get_current_user)):
    _require_human(current_user)
    persona = await persona_identity_service.get_persona(persona_id, current_user["id"])
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )
    return PersonaProfile(**persona)


@router.patch("/{persona_id}", response_model=PersonaProfile)
async def update_persona(
    persona_id: UUID,
    req: PersonaUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_human(current_user)
    persona = await persona_identity_service.update_persona(
        persona_id=persona_id,
        owner_id=current_user["id"],
        display_name=req.display_name,
        description=req.description,
    )
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )
    return PersonaProfile(**persona)


@router.post("/{persona_id}/rotate-key", response_model=PersonaResponse)
async def rotate_key(persona_id: UUID, current_user: dict = Depends(get_current_user)):
    _require_human(current_user)
    result = await persona_identity_service.rotate_persona_key(
        persona_id, current_user["id"]
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )
    persona, api_key = result
    return PersonaResponse(**persona, api_key=api_key)


@router.delete("/{persona_id}", status_code=204)
async def delete_persona(
    persona_id: UUID, current_user: dict = Depends(get_current_user)
):
    _require_human(current_user)
    deleted = await persona_identity_service.delete_persona(persona_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )


# ---------------------------------------------------------------------------
# Persona resource endpoints — authenticated as the persona itself
# ---------------------------------------------------------------------------


def _require_persona(user: dict) -> dict:
    """Require the caller to be a persona. Returns the user dict."""
    if user["type"] != "persona":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only persona users can access persona resources",
        )
    return user


def _get_notebook_id(user: dict) -> UUID:
    nb_id = user.get("notebook_id")
    if not nb_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona has no provisioned notebook. Re-create or provision the persona.",
        )
    return nb_id


def _get_history_id(user: dict) -> UUID:
    hist_id = user.get("history_id")
    if not hist_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona has no provisioned history. Re-create or provision the persona.",
        )
    return hist_id


# --- Notebook ---


@router.get("/me/notebook", response_model=NotebookResponse)
async def get_my_notebook(current_user: dict = Depends(get_current_user)):
    persona = _require_persona(current_user)
    nb_id = _get_notebook_id(persona)
    nb = await notebook_service.get_notebook(nb_id)
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return NotebookResponse(**nb)


@router.get("/me/notebook/sync-manifest", response_model=SyncManifestResponse)
async def get_sync_manifest(current_user: dict = Depends(get_current_user)):
    persona = _require_persona(current_user)
    nb_id = _get_notebook_id(persona)
    pages = await notebook_service.get_sync_manifest(nb_id)
    return SyncManifestResponse(notebook_id=nb_id, pages=pages)


@router.post("/me/notebook/pages", response_model=PageResponse, status_code=201)
async def create_persona_page(
    req: PersonaPageCreateRequest, current_user: dict = Depends(get_current_user),
):
    persona = _require_persona(current_user)
    nb_id = _get_notebook_id(persona)
    page = await notebook_service.create_page(
        notebook_id=nb_id, name=req.name, created_by=persona["id"],
        content=req.content, metadata=req.metadata,
    )
    return PageResponse(**page)


@router.get("/me/notebook/pages/{page_id}", response_model=PageResponse)
async def get_persona_page(
    page_id: UUID, current_user: dict = Depends(get_current_user),
):
    persona = _require_persona(current_user)
    nb_id = _get_notebook_id(persona)
    page = await notebook_service.get_page(page_id, nb_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.patch("/me/notebook/pages/{page_id}", response_model=PageResponse)
async def update_persona_page(
    page_id: UUID,
    req: PersonaPageUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    persona = _require_persona(current_user)
    nb_id = _get_notebook_id(persona)
    page = await notebook_service.update_page(
        page_id=page_id, notebook_id=nb_id, updated_by=persona["id"],
        name=req.name, content=req.content, metadata=req.metadata,
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.delete("/me/notebook/pages/{page_id}", status_code=204)
async def delete_persona_page(
    page_id: UUID, current_user: dict = Depends(get_current_user),
):
    persona = _require_persona(current_user)
    nb_id = _get_notebook_id(persona)
    deleted = await notebook_service.delete_page(page_id, nb_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")


# --- History ---


@router.get("/me/history", response_model=HistoryResponse)
async def get_my_history(current_user: dict = Depends(get_current_user)):
    persona = _require_persona(current_user)
    hist_id = _get_history_id(persona)
    store = await memory_service.get_store(hist_id, workspace_id=None, user_id=persona["id"])
    if not store:
        raise HTTPException(status_code=404, detail="History not found")
    return HistoryResponse(**store)


@router.post("/me/history/events", response_model=HistoryEventResponse, status_code=201)
async def push_persona_event(
    req: HistoryEventCreateRequest, current_user: dict = Depends(get_current_user),
):
    persona = _require_persona(current_user)
    hist_id = _get_history_id(persona)
    event = await memory_service.push_event(
        store_id=hist_id,
        agent_name=req.agent_name,
        event_type=req.event_type,
        content=req.content,
        session_id=req.session_id,
        tool_name=req.tool_name,
        metadata=req.metadata,
    )
    return HistoryEventResponse(**event)


@router.post("/me/history/events/batch", response_model=list[HistoryEventResponse], status_code=201)
async def push_persona_events_batch(
    req: HistoryEventBatchRequest, current_user: dict = Depends(get_current_user),
):
    persona = _require_persona(current_user)
    hist_id = _get_history_id(persona)
    events = await memory_service.push_events_batch(
        hist_id, [e.model_dump() for e in req.events],
    )
    return [HistoryEventResponse(**e) for e in events]


@router.get("/me/history/events", response_model=HistoryEventListResponse)
async def query_persona_events(
    current_user: dict = Depends(get_current_user),
    agent_name: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
):
    persona = _require_persona(current_user)
    hist_id = _get_history_id(persona)
    events, has_more = await memory_service.query_events(
        hist_id,
        agent_name=agent_name,
        session_id=session_id,
        event_type=event_type,
        after=after,
        before=before,
        limit=limit,
    )
    return HistoryEventListResponse(
        events=[HistoryEventResponse(**e) for e in events],
        has_more=has_more,
    )


# --- Injection ---


@router.post("/me/inject", response_model=InjectionResponse)
async def inject_context(
    req: InjectionRequest,
    current_user: dict = Depends(get_current_user),
):
    """Compute scored injection context for the persona's prompt."""
    persona = _require_persona(current_user)
    nb_id = _get_notebook_id(persona)
    hist_id = _get_history_id(persona)

    result = await injection_service.compute_injection(
        agent_id=persona["id"],
        notebook_id=nb_id,
        history_id=hist_id,
        prompt_text=req.prompt_text,
        session_state_data=req.session_state.model_dump(),
        session_id=req.session_id,
    )
    return InjectionResponse(**result)


# --- Sleep Agent ---


@router.post("/me/sleep")
async def trigger_sleep(current_user: dict = Depends(get_current_user)):
    """Manually trigger sleep agent curation for the calling persona."""
    persona = _require_persona(current_user)
    result = await sleep_service.curate(persona["id"])
    return result


@router.get("/me/sleep/status")
async def sleep_status(current_user: dict = Depends(get_current_user)):
    """Get sleep agent status: watermark, last run, config."""
    persona = _require_persona(current_user)
    from ..database import get_pool
    pool = get_pool()

    watermark = await pool.fetchrow(
        "SELECT last_event_at, last_monologue_event_at, last_run_at "
        "FROM sleep_watermarks WHERE persona_id = $1",
        persona["id"],
    )
    config = await pool.fetchrow(
        "SELECT enabled, interval_minutes, max_pattern_cards "
        "FROM sleep_configs WHERE persona_id = $1",
        persona["id"],
    )

    return {
        "watermark": dict(watermark) if watermark else None,
        "config": dict(config) if config else {"enabled": True, "interval_minutes": 60, "max_pattern_cards": 500},
    }


@router.post("/me/backfill-embeddings")
async def backfill_embeddings(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """Backfill embeddings for existing events that don't have them.

    Call this after deploying pgvector to embed historical events.
    Processes up to `limit` events per call.
    """
    from ..services import embedding_service

    if not embedding_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service not configured (EMBEDDING_API_KEY not set)",
        )

    persona = _require_persona(current_user)
    hist_id = _get_history_id(persona)

    from ..database import get_pool
    pool = get_pool()

    # Get events without embeddings
    rows = await pool.fetch(
        "SELECT id, content FROM history_events "
        "WHERE store_id = $1 AND embedding IS NULL "
        "ORDER BY created_at DESC LIMIT $2",
        hist_id, min(limit, 500),
    )

    if not rows:
        return {"status": "complete", "embedded": 0, "remaining": 0}

    # Batch embed
    texts = [r["content"] for r in rows]
    vecs = await embedding_service.embed_batch(texts)

    embedded = 0
    if vecs:
        async with pool.acquire() as conn:
            for row, vec in zip(rows, vecs):
                await conn.execute(
                    "UPDATE history_events SET embedding = $1 WHERE id = $2",
                    vec, row["id"],
                )
                embedded += 1

    # Check how many remain
    remaining = await pool.fetchval(
        "SELECT COUNT(*) FROM history_events WHERE store_id = $1 AND embedding IS NULL",
        hist_id,
    )

    return {"status": "in_progress" if remaining > 0 else "complete", "embedded": embedded, "remaining": remaining}


# --- Chat Watches ---


@router.get("/me/unread", response_model=UnreadListResponse)
async def get_unread(current_user: dict = Depends(get_current_user)):
    """Get unread message counts across all watched chats."""
    persona = _require_persona(current_user)
    items = await watch_service.get_unread(persona["id"])
    return UnreadListResponse(
        unread=[UnreadChatResponse(**i) for i in items],
        total_unread=sum(i["unread_count"] for i in items),
    )


@router.get("/me/watches", response_model=WatchListResponse)
async def list_watches(current_user: dict = Depends(get_current_user)):
    """List all active chat watches."""
    persona = _require_persona(current_user)
    watches = await watch_service.list_watches(persona["id"])
    return WatchListResponse(watches=[WatchResponse(**w) for w in watches])


@router.post("/me/watches/{chat_id}", response_model=WatchResponse, status_code=201)
async def add_watch(
    chat_id: UUID,
    workspace_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Watch a chat for new messages."""
    persona = _require_persona(current_user)
    try:
        watch = await watch_service.watch_chat(persona["id"], chat_id, workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return WatchResponse(**watch)


@router.delete("/me/watches/{chat_id}", status_code=204)
async def remove_watch(
    chat_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Stop watching a chat."""
    persona = _require_persona(current_user)
    removed = await watch_service.unwatch_chat(persona["id"], chat_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")


@router.post("/me/watches/{chat_id}/mark-read")
async def mark_read(
    chat_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Mark a watched chat as read."""
    persona = _require_persona(current_user)
    updated = await watch_service.mark_read(persona["id"], chat_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    return {"status": "ok"}
