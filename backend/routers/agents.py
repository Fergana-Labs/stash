"""Named agent configs — CRUD. The default agent is auto-created on first list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import get_current_user
from ..services import agent_service

router = APIRouter(prefix="/api/v1/me/agents", tags=["agents"])


class AgentFields(BaseModel):
    name: str | None = None
    model_provider: str | None = None  # anthropic | openai | openrouter | null(auto)
    system_prompt: str | None = None
    run_mode: str = "chat"
    schedule_cron: str | None = None
    schedule_prompt: str | None = None
    slack_bound: bool = False
    telegram_bound: bool = False


@router.get("")
async def list_agents(current_user: dict = Depends(get_current_user)):
    # Ensure the default exists so the list is never empty.
    await agent_service.get_or_create_default(current_user["id"])
    return {"agents": await agent_service.list_agents(current_user["id"])}


@router.post("")
async def create_agent(fields: AgentFields, current_user: dict = Depends(get_current_user)):
    return await agent_service.create_agent(current_user["id"], fields.model_dump())


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: UUID, fields: AgentFields, current_user: dict = Depends(get_current_user)
):
    # exclude_unset so a partial PATCH only touches the fields it sent (the
    # service merges over current), rather than resetting the rest to defaults.
    return await agent_service.update_agent(
        current_user["id"], agent_id, fields.model_dump(exclude_unset=True)
    )


@router.delete("/{agent_id}")
async def delete_agent(agent_id: UUID, current_user: dict = Depends(get_current_user)):
    await agent_service.delete_agent(current_user["id"], agent_id)
    return {"ok": True}
