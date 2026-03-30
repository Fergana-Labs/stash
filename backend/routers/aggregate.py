"""Aggregate router: cross-workspace views for the authenticated user."""

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..services import chat_service, deck_service, memory_service, notebook_service, agent_identity_service

router = APIRouter(prefix="/api/v1/me", tags=["aggregate"])


@router.get("/chats")
async def list_all_chats(current_user: dict = Depends(get_current_user)):
    """All chats: workspace chats + personal rooms + DMs."""
    result = await chat_service.list_all_user_chats(current_user["id"])
    return result


@router.get("/notebooks")
async def list_all_notebooks(current_user: dict = Depends(get_current_user)):
    """All notebooks from workspaces + personal."""
    notebooks = await notebook_service.list_all_user_notebooks(current_user["id"])
    return {"notebooks": notebooks}


@router.get("/history")
async def list_all_histories(current_user: dict = Depends(get_current_user)):
    """All historys from workspaces + personal."""
    stores = await memory_service.list_all_user_stores(current_user["id"])
    return {"stores": stores}


@router.get("/history-events")
async def list_all_history_events(
    agent_name: str | None = Query(None),
    event_type: str | None = Query(None),
    after: str | None = Query(None),
    before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Events across all accessible stores with filters."""
    events, has_more = await memory_service.query_all_user_events(
        current_user["id"],
        agent_name=agent_name,
        event_type=event_type,
        after=after,
        before=before,
        limit=limit,
    )
    return {"events": events, "has_more": has_more}


@router.get("/agents")
async def list_agents_with_context(current_user: dict = Depends(get_current_user)):
    """User's agents with workspace membership context."""
    from ..database import get_pool
    pool = get_pool()

    agents = await agent_identity_service.list_owner_agents(current_user["id"])
    result = []
    for agent in agents:
        a = dict(agent)
        # Find workspaces this agent is a member of
        ws_rows = await pool.fetch(
            "SELECT wm.workspace_id, wm.role, w.name AS workspace_name "
            "FROM workspace_members wm "
            "JOIN workspaces w ON w.id = wm.workspace_id "
            "WHERE wm.user_id = $1",
            a["id"],
        )
        a["workspaces"] = [dict(r) for r in ws_rows]
        result.append(a)
    return {"agents": result}


@router.get("/decks")
async def list_all_decks(current_user: dict = Depends(get_current_user)):
    """All decks from workspaces + personal."""
    decks = await deck_service.list_all_user_decks(current_user["id"])
    return {"decks": decks}
