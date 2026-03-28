from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_user
from ..models import (
    AgentCreateRequest, AgentPageCreateRequest, AgentPageUpdateRequest,
    AgentProfile, AgentResponse, AgentUpdateRequest,
    HistoryEventBatchRequest, HistoryEventCreateRequest,
    HistoryEventListResponse, HistoryEventResponse, HistoryResponse,
    InjectionRequest, InjectionResponse,
    NotebookResponse, PageResponse, SyncManifestResponse,
)
from ..services import agent_identity_service, injection_service, memory_service, notebook_service, sleep_service

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _require_human(user: dict) -> None:
    if user["type"] != "human":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only human users can manage agent identities",
        )


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    req: AgentCreateRequest, current_user: dict = Depends(get_current_user)
):
    _require_human(current_user)
    try:
        agent, api_key = await agent_identity_service.create_agent(
            owner_id=current_user["id"],
            name=req.name,
            display_name=req.display_name,
            description=req.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return AgentResponse(**agent, api_key=api_key)


@router.get("", response_model=list[AgentProfile])
async def list_agents(current_user: dict = Depends(get_current_user)):
    _require_human(current_user)
    agents = await agent_identity_service.list_owner_agents(current_user["id"])
    return [AgentProfile(**a) for a in agents]


@router.get("/{agent_id}", response_model=AgentProfile)
async def get_agent(agent_id: UUID, current_user: dict = Depends(get_current_user)):
    _require_human(current_user)
    agent = await agent_identity_service.get_agent(agent_id, current_user["id"])
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return AgentProfile(**agent)


@router.patch("/{agent_id}", response_model=AgentProfile)
async def update_agent(
    agent_id: UUID,
    req: AgentUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_human(current_user)
    agent = await agent_identity_service.update_agent(
        agent_id=agent_id,
        owner_id=current_user["id"],
        display_name=req.display_name,
        description=req.description,
    )
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return AgentProfile(**agent)


@router.post("/{agent_id}/rotate-key", response_model=AgentResponse)
async def rotate_key(agent_id: UUID, current_user: dict = Depends(get_current_user)):
    _require_human(current_user)
    result = await agent_identity_service.rotate_agent_key(
        agent_id, current_user["id"]
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    agent, api_key = result
    return AgentResponse(**agent, api_key=api_key)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: UUID, current_user: dict = Depends(get_current_user)
):
    _require_human(current_user)
    deleted = await agent_identity_service.delete_agent(agent_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )


# ---------------------------------------------------------------------------
# Agent resource endpoints — authenticated as the agent itself
# ---------------------------------------------------------------------------


def _require_agent(user: dict) -> dict:
    """Require the caller to be an agent. Returns the user dict."""
    if user["type"] != "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agent users can access agent resources",
        )
    return user


def _get_notebook_id(user: dict) -> UUID:
    nb_id = user.get("notebook_id")
    if not nb_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent has no provisioned notebook. Re-create or provision the agent.",
        )
    return nb_id


def _get_history_id(user: dict) -> UUID:
    hist_id = user.get("history_id")
    if not hist_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent has no provisioned history. Re-create or provision the agent.",
        )
    return hist_id


# --- Notebook ---


@router.get("/me/notebook", response_model=NotebookResponse)
async def get_my_notebook(current_user: dict = Depends(get_current_user)):
    agent = _require_agent(current_user)
    nb_id = _get_notebook_id(agent)
    nb = await notebook_service.get_notebook(nb_id)
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return NotebookResponse(**nb)


@router.get("/me/notebook/sync-manifest", response_model=SyncManifestResponse)
async def get_sync_manifest(current_user: dict = Depends(get_current_user)):
    agent = _require_agent(current_user)
    nb_id = _get_notebook_id(agent)
    pages = await notebook_service.get_sync_manifest(nb_id)
    return SyncManifestResponse(notebook_id=nb_id, pages=pages)


@router.post("/me/notebook/pages", response_model=PageResponse, status_code=201)
async def create_agent_page(
    req: AgentPageCreateRequest, current_user: dict = Depends(get_current_user),
):
    agent = _require_agent(current_user)
    nb_id = _get_notebook_id(agent)
    page = await notebook_service.create_page(
        notebook_id=nb_id, name=req.name, created_by=agent["id"],
        content=req.content, metadata=req.metadata,
    )
    return PageResponse(**page)


@router.get("/me/notebook/pages/{page_id}", response_model=PageResponse)
async def get_agent_page(
    page_id: UUID, current_user: dict = Depends(get_current_user),
):
    agent = _require_agent(current_user)
    nb_id = _get_notebook_id(agent)
    page = await notebook_service.get_page(page_id, nb_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.patch("/me/notebook/pages/{page_id}", response_model=PageResponse)
async def update_agent_page(
    page_id: UUID,
    req: AgentPageUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    agent = _require_agent(current_user)
    nb_id = _get_notebook_id(agent)
    page = await notebook_service.update_page(
        page_id=page_id, notebook_id=nb_id, updated_by=agent["id"],
        name=req.name, content=req.content, metadata=req.metadata,
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.delete("/me/notebook/pages/{page_id}", status_code=204)
async def delete_agent_page(
    page_id: UUID, current_user: dict = Depends(get_current_user),
):
    agent = _require_agent(current_user)
    nb_id = _get_notebook_id(agent)
    deleted = await notebook_service.delete_page(page_id, nb_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")


# --- History ---


@router.get("/me/history", response_model=HistoryResponse)
async def get_my_history(current_user: dict = Depends(get_current_user)):
    agent = _require_agent(current_user)
    hist_id = _get_history_id(agent)
    store = await memory_service.get_personal_store(hist_id, agent["id"])
    if not store:
        raise HTTPException(status_code=404, detail="History not found")
    return HistoryResponse(**store)


@router.post("/me/history/events", response_model=HistoryEventResponse, status_code=201)
async def push_agent_event(
    req: HistoryEventCreateRequest, current_user: dict = Depends(get_current_user),
):
    agent = _require_agent(current_user)
    hist_id = _get_history_id(agent)
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
async def push_agent_events_batch(
    req: HistoryEventBatchRequest, current_user: dict = Depends(get_current_user),
):
    agent = _require_agent(current_user)
    hist_id = _get_history_id(agent)
    events = await memory_service.push_events_batch(
        hist_id, [e.model_dump() for e in req.events],
    )
    return [HistoryEventResponse(**e) for e in events]


@router.get("/me/history/events", response_model=HistoryEventListResponse)
async def query_agent_events(
    current_user: dict = Depends(get_current_user),
    agent_name: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
):
    agent = _require_agent(current_user)
    hist_id = _get_history_id(agent)
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
    """Compute scored injection context for the agent's prompt."""
    agent = _require_agent(current_user)
    nb_id = _get_notebook_id(agent)
    hist_id = _get_history_id(agent)

    result = await injection_service.compute_injection(
        agent_id=agent["id"],
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
    """Manually trigger sleep agent curation for the calling agent."""
    agent = _require_agent(current_user)
    result = await sleep_service.curate(agent["id"])
    return result


@router.get("/me/sleep/status")
async def sleep_status(current_user: dict = Depends(get_current_user)):
    """Get sleep agent status: watermark, last run, config."""
    agent = _require_agent(current_user)
    from ..database import get_pool
    pool = get_pool()

    watermark = await pool.fetchrow(
        "SELECT last_event_at, last_monologue_event_at, last_run_at "
        "FROM sleep_watermarks WHERE agent_id = $1",
        agent["id"],
    )
    config = await pool.fetchrow(
        "SELECT enabled, interval_minutes, max_pattern_cards "
        "FROM sleep_configs WHERE agent_id = $1",
        agent["id"],
    )

    return {
        "watermark": dict(watermark) if watermark else None,
        "config": dict(config) if config else {"enabled": True, "interval_minutes": 60, "max_pattern_cards": 500},
    }
