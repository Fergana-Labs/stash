"""Named agent configs — CRUD. The default agent is auto-created on first list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth import get_current_user
from ..database import get_pool
from ..services import agent_service, sprite_agent_service

router = APIRouter(prefix="/api/v1/me/agents", tags=["agents"])


class AgentFields(BaseModel):
    name: str | None = None
    model_provider: str | None = None  # anthropic | openai | openrouter | local | null(auto)
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


@router.get("/{agent_id}")
async def get_agent(agent_id: UUID, current_user: dict = Depends(get_current_user)):
    return await agent_service.get_agent(current_user["id"], agent_id)


@router.get("/{agent_id}/runs")
async def list_agent_runs(
    agent_id: UUID,
    limit: int = Query(30, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """A scheduled agent's newest runs as one chronological feed."""
    agent = await agent_service.get_agent(current_user["id"], agent_id)
    prefix = sprite_agent_service.scheduled_session_prefix(agent)
    rows = await get_pool().fetch(
        """
        WITH newest_sessions AS (
            SELECT session_id, MIN(created_at) AS started_at
            FROM history_events
            WHERE owner_user_id = $1
              AND session_id LIKE $2
            GROUP BY session_id
            ORDER BY started_at DESC, session_id DESC
            LIMIT $3
        )
        SELECT
            he.session_id,
            MIN(he.created_at) AS started_at,
            MAX(he.created_at) AS last_event_at,
            COUNT(*)::int AS event_count,
            COUNT(*) FILTER (WHERE he.event_type = 'tool_use')::int AS tool_count,
            (ARRAY_AGG(he.content ORDER BY he.created_at DESC, he.id DESC)
                FILTER (WHERE he.event_type = 'assistant_message'))[1] AS final_text,
            COALESCE(
                JSONB_AGG(
                    JSONB_BUILD_OBJECT(
                        'role', REPLACE(he.event_type, '_message', ''),
                        'content', he.content
                    )
                    ORDER BY he.created_at, he.id
                ) FILTER (
                    WHERE he.event_type IN ('user_message', 'assistant_message')
                      AND NULLIF(BTRIM(he.content), '') IS NOT NULL
                ),
                '[]'::jsonb
            ) AS messages
        FROM history_events he
        JOIN newest_sessions ns ON ns.session_id = he.session_id
        WHERE he.owner_user_id = $1
        GROUP BY he.session_id
        ORDER BY started_at, he.session_id
        """,
        current_user["id"],
        f"{prefix}%",
        limit,
    )
    return {"runs": [await _run_from_row(row) for row in rows]}


async def _run_from_row(row: dict) -> dict:
    final_text = row["final_text"]
    if final_text is None:
        status = (
            "running"
            if await sprite_agent_service.turn_running(row["session_id"])
            else "interrupted"
        )
        error = None
    elif final_text.startswith(sprite_agent_service.RUN_FAILED_PREFIX):
        status = "failed"
        error = final_text.removeprefix(sprite_agent_service.RUN_FAILED_PREFIX).strip()
    elif final_text == sprite_agent_service.STOPPED_NOTE:
        status = "stopped"
        error = None
    else:
        status = "completed"
        error = None

    finished_at = row["last_event_at"] if status in {"completed", "failed", "stopped"} else None
    duration_seconds = (
        (finished_at - row["started_at"]).total_seconds() if finished_at is not None else None
    )
    return {
        "session_id": row["session_id"],
        "started_at": row["started_at"],
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "event_count": row["event_count"],
        "tool_count": row["tool_count"],
        "status": status,
        "error": error,
        "messages": row["messages"],
    }


@router.get("/{agent_id}/prompt")
async def get_agent_prompt(agent_id: UUID, current_user: dict = Depends(get_current_user)):
    """The exact prompts a scheduled agent runs: the appended system prompt and
    the per-run instruction. For the Memory curator this is built server-side
    (not a user field), so the UI shows it read-only."""
    from fastapi import HTTPException

    agent = await agent_service.get_agent(current_user["id"], agent_id)
    if agent["run_mode"] != "scheduled":
        raise HTTPException(status_code=400, detail="Only scheduled agents run a fixed prompt.")
    owner_name = current_user["display_name"] or current_user["name"]
    _, run_prompt = await sprite_agent_service.build_scheduled_turn(agent, "preview")
    return {
        "system_prompt": sprite_agent_service._system_prompt(owner_name, agent["system_prompt"]),
        "run_prompt": run_prompt,
    }


@router.delete("/{agent_id}")
async def delete_agent(agent_id: UUID, current_user: dict = Depends(get_current_user)):
    await agent_service.delete_agent(current_user["id"], agent_id)
    return {"ok": True}
