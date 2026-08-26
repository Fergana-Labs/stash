"""The curator log: what we learned from each nightly curation.

One entry per curator run — the run's stored final message, which the
curation prompt constrains to a one-sentence learning. File activity lives
in its own feed; this log is only the synthesis.
"""

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..database import get_pool
from ..services import agent_service
from ..services.sprite_agent_service import (
    RUN_FAILED_PREFIX,
    RUN_SKIPPED_PREFIX,
    STOPPED_NOTE,
    scheduled_session_prefix,
    turn_running,
)

router = APIRouter(prefix="/api/v1/me", tags=["curator-log"])


@router.get("/curator-log")
async def curator_log(
    limit: int = Query(14, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
) -> dict:
    user_id = current_user["id"]
    curator = await agent_service.get_or_create_curator(user_id)
    return {"entries": await curator_runs(user_id, curator, limit)}


async def curator_runs(user_id, curator: dict, limit: int = 14) -> list[dict]:
    """One entry per run of this curator, newest first. Shared with the
    developer console, which shows the external curator's history."""
    prefix = scheduled_session_prefix(curator)
    pool = get_pool()
    runs = await pool.fetch(
        """
        SELECT session_id, MIN(created_at) AS started_at,
               (ARRAY_AGG(content ORDER BY created_at DESC, id DESC)
                  FILTER (WHERE event_type = 'assistant_message'))[1] AS final_text
        FROM history_events
        WHERE owner_user_id = $1 AND session_id LIKE $2
        GROUP BY session_id
        ORDER BY started_at DESC
        LIMIT $3
        """,
        user_id,
        f"{prefix}%",
        limit,
    )
    return [await _entry(dict(run)) for run in runs]


async def _entry(run: dict) -> dict:
    final_text = run["final_text"]
    if final_text is None:
        # Tonight's pass is still writing: no final message yet. The turn lock
        # is what separates it from a run that died before writing one.
        status = "running" if await turn_running(run["session_id"]) else "interrupted"
        summary, error = None, None
    elif final_text.startswith(RUN_FAILED_PREFIX):
        status, summary = "failed", None
        error = final_text.removeprefix(RUN_FAILED_PREFIX).strip()
    elif final_text.startswith(RUN_SKIPPED_PREFIX):
        # A skipped night is a real answer ("nothing new"), not a missing one.
        status = "skipped"
        summary = final_text.removeprefix(RUN_SKIPPED_PREFIX).strip()
        error = None
    elif final_text == STOPPED_NOTE:
        status, summary, error = "stopped", None, None
    else:
        status, summary, error = "completed", final_text, None

    return {
        "session_id": run["session_id"],
        "started_at": run["started_at"].isoformat(),
        "status": status,
        "summary": summary,
        "error": error,
    }
