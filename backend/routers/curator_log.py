"""The curator log: what we learned from each nightly curation.

One entry per curator run — the run's stored final message, which the
curation prompt constrains to a one-sentence learning. File activity lives
in its own feed; this log is only the synthesis.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ..auth import get_scope
from ..database import get_pool
from ..services import agent_service
from ..services.sprite_agent_service import (
    RUN_FAILED_PREFIX,
    STOPPED_NOTE,
    scheduled_session_prefix,
    turn_running,
)

router = APIRouter(prefix="/api/v1/me", tags=["curator-log"])


@router.get("/curator-log")
async def curator_log(
    limit: int = Query(14, ge=1, le=50),
    scope: UUID = Depends(get_scope),
) -> dict:
    # Each scope has its own curator, so a stash's home shows that stash's
    # curation story — never another stash's.
    user_id = scope
    curator = await agent_service.get_or_create_curator(user_id)
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
    return {"entries": [await _entry(dict(run)) for run in runs]}


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
