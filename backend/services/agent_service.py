"""Named, configurable agents — CRUD and the per-turn config a run needs.

An agent is a saved configuration: its model (a provider override), persona
(extra system prompt), run mode (chat vs scheduled), and channel bindings.
Every user has one auto-created default agent; chats and channels resolve to an
agent, whose config shapes the turn.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException

from ..database import get_pool

_COLUMNS = (
    "id, user_id, name, model_provider, system_prompt, run_mode, "
    "schedule_cron, schedule_prompt, is_default, is_curator, slack_bound, "
    "telegram_bound, last_run_at, last_run_error, curated_through, "
    "month_run_count, month_run_anchor, created_at"
)


# The daily curator's cron is staggered per user so sprite wakes spread across
# the day rather than all firing at once.
def _staggered_daily_cron(user_id: UUID) -> str:
    n = int.from_bytes(user_id.bytes, "big")
    return f"{n % 60} {n % 24} * * *"


_VALID_PROVIDERS = {"anthropic", "openai", "openrouter"}
_VALID_RUN_MODES = {"chat", "scheduled"}


def _row(row) -> dict:
    d = dict(row)
    d["id"] = str(d["id"])
    return d


async def list_agents(user_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        f"SELECT {_COLUMNS} FROM agents WHERE user_id = $1 ORDER BY is_default DESC, created_at",
        user_id,
    )
    return [_row(r) for r in rows]


async def get_agent(user_id: UUID, agent_id: UUID) -> dict:
    row = await get_pool().fetchrow(
        f"SELECT {_COLUMNS} FROM agents WHERE id = $1 AND user_id = $2", agent_id, user_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _row(row)


async def get_agent_by_id(agent_id: UUID) -> dict:
    """Unscoped fetch for internal tasks — the enqueuing router already
    authorized the caller."""
    row = await get_pool().fetchrow(f"SELECT {_COLUMNS} FROM agents WHERE id = $1", agent_id)
    if row is None:
        raise ValueError(f"agent {agent_id} not found")
    return _row(row)


async def get_or_create_default(user_id: UUID) -> dict:
    """The user's default agent, created on first use."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_COLUMNS} FROM agents WHERE user_id = $1 AND is_default", user_id
    )
    if row is not None:
        return _row(row)
    row = await pool.fetchrow(
        f"""
        INSERT INTO agents (user_id, name, is_default)
        VALUES ($1, 'Stash Agent', true)
        ON CONFLICT (user_id) WHERE is_default DO NOTHING
        RETURNING {_COLUMNS}
        """,
        user_id,
    )
    if row is None:  # lost the race — read the winner.
        row = await pool.fetchrow(
            f"SELECT {_COLUMNS} FROM agents WHERE user_id = $1 AND is_default", user_id
        )
    return _row(row)


# How far back the first curation looks (the wiki bootstraps from this window).
CURATOR_BACKFILL_DAYS = 90


async def get_or_create_curator(user_id: UUID) -> dict:
    """The user's reserved Memory-curator agent, created on first use.

    Scheduled daily (staggered). Both the cron baseline (last_run_at) and the
    delta watermark (curated_through) seed to a bounded backfill point, so the
    first run is due immediately and bootstraps from real history."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_COLUMNS} FROM agents WHERE user_id = $1 AND is_curator", user_id
    )
    if row is not None:
        return _row(row)
    row = await pool.fetchrow(
        f"""
        INSERT INTO agents (user_id, name, run_mode, schedule_cron, is_curator,
                            last_run_at, curated_through)
        SELECT $1, 'Memory curator', 'scheduled', $2, true, backfill, backfill
        FROM (SELECT greatest((SELECT created_at FROM users WHERE id = $1),
                              now() - make_interval(days => $3)) AS backfill) seed
        ON CONFLICT (user_id) WHERE is_curator DO NOTHING
        RETURNING {_COLUMNS}
        """,
        user_id,
        _staggered_daily_cron(user_id),
        CURATOR_BACKFILL_DAYS,
    )
    if row is None:  # lost the race — read the winner.
        row = await pool.fetchrow(
            f"SELECT {_COLUMNS} FROM agents WHERE user_id = $1 AND is_curator", user_id
        )
    return _row(row)


def _validate(model_provider, run_mode, schedule_cron) -> None:
    if model_provider is not None and model_provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"invalid model_provider: {model_provider}")
    if run_mode not in _VALID_RUN_MODES:
        raise HTTPException(status_code=400, detail=f"invalid run_mode: {run_mode}")
    if run_mode == "scheduled" and not schedule_cron:
        raise HTTPException(status_code=400, detail="scheduled agents need a schedule_cron")


async def create_agent(user_id: UUID, fields: dict) -> dict:
    run_mode = fields.get("run_mode", "chat")
    _validate(fields.get("model_provider"), run_mode, fields.get("schedule_cron"))
    row = await get_pool().fetchrow(
        f"""
        INSERT INTO agents (user_id, name, model_provider, system_prompt,
                            run_mode, schedule_cron, schedule_prompt, last_run_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7,
                CASE WHEN $5 = 'scheduled' THEN now() ELSE NULL END)
        RETURNING {_COLUMNS}
        """,
        user_id,
        (fields.get("name") or "Agent").strip()[:80],
        fields.get("model_provider"),
        fields.get("system_prompt"),
        run_mode,
        fields.get("schedule_cron"),
        fields.get("schedule_prompt"),
    )
    return _row(row)


async def update_agent(user_id: UUID, agent_id: UUID, fields: dict) -> dict:
    current = await get_agent(user_id, agent_id)
    merged = {**current, **fields}
    _validate(
        merged.get("model_provider"), merged.get("run_mode", "chat"), merged.get("schedule_cron")
    )

    async with get_pool().acquire() as conn, conn.transaction():
        # Channel bindings are unique per user; clear others in the same tx so
        # the partial unique index can't transiently see two bound agents.
        if merged.get("slack_bound"):
            await conn.execute(
                "UPDATE agents SET slack_bound = false WHERE user_id = $1 AND id <> $2",
                user_id,
                agent_id,
            )
        if merged.get("telegram_bound"):
            await conn.execute(
                "UPDATE agents SET telegram_bound = false WHERE user_id = $1 AND id <> $2",
                user_id,
                agent_id,
            )
        # Seed last_run_at when the agent first becomes scheduled, so the cron
        # has a baseline (a NULL baseline never becomes due).
        row = await conn.fetchrow(
            f"""
            UPDATE agents SET
                name = $3, model_provider = $4, system_prompt = $5, run_mode = $6,
                schedule_cron = $7, schedule_prompt = $8, slack_bound = $9, telegram_bound = $10,
                last_run_at = CASE
                    WHEN $6 = 'scheduled' AND last_run_at IS NULL THEN now()
                    WHEN $6 <> 'scheduled' THEN NULL
                    ELSE last_run_at END
            WHERE id = $1 AND user_id = $2
            RETURNING {_COLUMNS}
            """,
            agent_id,
            user_id,
            (merged.get("name") or "Agent").strip()[:80],
            merged.get("model_provider"),
            merged.get("system_prompt"),
            merged.get("run_mode", "chat"),
            merged.get("schedule_cron"),
            merged.get("schedule_prompt"),
            bool(merged.get("slack_bound")),
            bool(merged.get("telegram_bound")),
        )
    return _row(row)


async def delete_agent(user_id: UUID, agent_id: UUID) -> None:
    agent = await get_agent(user_id, agent_id)
    if agent["is_default"]:
        raise HTTPException(status_code=400, detail="cannot delete the default agent")
    if agent["is_curator"]:
        raise HTTPException(
            status_code=400, detail="cannot delete the Memory curator (turn it off instead)"
        )
    await get_pool().execute("DELETE FROM agents WHERE id = $1 AND user_id = $2", agent_id, user_id)


async def list_scheduled() -> list[dict]:
    """All scheduled agents due for the beat task's check. The curator runs the
    curation prompt (no schedule_prompt); other scheduled agents need one."""
    rows = await get_pool().fetch(
        f"SELECT {_COLUMNS} FROM agents "
        "WHERE run_mode = 'scheduled' AND schedule_cron IS NOT NULL "
        "AND (is_curator OR schedule_prompt IS NOT NULL)"
    )
    return [_row(r) for r in rows]


def month_runs_used(agent: dict) -> int:
    """Scheduled runs consumed in the current calendar month. An anchor from a
    prior month means the counter is stale; mark_run resets it on the next run."""
    anchor = agent.get("month_run_anchor")
    today = date.today()
    if anchor is None or (anchor.year, anchor.month) != (today.year, today.month):
        return 0
    return agent["month_run_count"]


async def mark_run(agent_id: UUID) -> int:
    """Consume the cron tick and meter the run against the calendar month.
    Returns the run count within the current month (including this one) —
    the free-tier curator credit gate reads it."""
    return await get_pool().fetchval(
        """
        UPDATE agents SET
            last_run_at = now(),
            month_run_count = CASE
                WHEN month_run_anchor = date_trunc('month', now())::date
                THEN month_run_count + 1 ELSE 1 END,
            month_run_anchor = date_trunc('month', now())::date
        WHERE id = $1
        RETURNING month_run_count
        """,
        agent_id,
    )


async def mark_run_failed(agent_id: UUID, error: str) -> None:
    """Stamp the failure where the API can surface it, and refund the month
    credit — an outage shouldn't eat the free allowance. The tick itself stays
    consumed (last_run_at), so the beat won't re-fire the same window."""
    await get_pool().execute(
        """
        UPDATE agents SET
            last_run_error = left($2, 500),
            month_run_count = greatest(month_run_count - 1, 0)
        WHERE id = $1
        """,
        agent_id,
        error,
    )


async def mark_run_succeeded(agent_id: UUID) -> None:
    await get_pool().execute("UPDATE agents SET last_run_error = NULL WHERE id = $1", agent_id)


async def mark_curated(agent_id: UUID, through) -> None:
    """Advance the curator's delta watermark — only after a successful run, so
    a failed run's window is re-covered next time."""
    await get_pool().execute(
        "UPDATE agents SET curated_through = $2 WHERE id = $1", agent_id, through
    )


async def channel_agent(user_id: UUID, channel: str) -> dict:
    """The agent bound to a channel ('slack'|'telegram'), or the default."""
    col = "slack_bound" if channel == "slack" else "telegram_bound"
    row = await get_pool().fetchrow(
        f"SELECT {_COLUMNS} FROM agents WHERE user_id = $1 AND {col}", user_id
    )
    return _row(row) if row is not None else await get_or_create_default(user_id)
