from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_user
from ..models import AgentCreateRequest, AgentProfile, AgentResponse, AgentUpdateRequest
from ..services import agent_identity_service

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
