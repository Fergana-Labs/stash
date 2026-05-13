from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.models import StashUpdateRequest
from backend.workers import session_summarizer


def test_session_share_update_rejects_client_status():
    with pytest.raises(ValidationError):
        StashUpdateRequest(summary="done", status="summarizing")


@pytest.mark.asyncio
async def test_summarize_one_claims_live_session_before_llm(pool, monkeypatch):
    user_id = uuid4()
    workspace_id = uuid4()

    await pool.execute(
        "INSERT INTO users (id, name) VALUES ($1, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    await pool.execute(
        "INSERT INTO workspaces (id, name, creator_id, invite_code) " "VALUES ($1, $2, $3, $4)",
        workspace_id,
        f"ws_{workspace_id.hex[:6]}",
        user_id,
        workspace_id.hex[:12],
    )
    session_id = await pool.fetchval(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, 'session-1', 'alice-agent', $2) "
        "RETURNING id",
        workspace_id,
        user_id,
    )
    await pool.execute(
        "INSERT INTO history_events "
        "(workspace_id, created_by, agent_name, event_type, session_id, content) "
        "VALUES ($1, $2, 'alice-agent', 'user_message', 'session-1', 'Fix auth')",
        workspace_id,
        user_id,
    )

    statuses_seen_by_llm = []
    stale_workspaces = []

    async def fake_one_shot(*args, **kwargs):
        status = await pool.fetchval("SELECT status FROM sessions WHERE id = $1", session_id)
        statuses_seen_by_llm.append(status)
        return session_summarizer.llm.OneShotResult(
            text="Implemented auth fix.",
            input_tokens=11,
            output_tokens=5,
            model="claude-test-fast",
        )

    async def fake_mark_stale(stale_workspace_id):
        stale_workspaces.append(stale_workspace_id)

    monkeypatch.setattr(session_summarizer.llm, "one_shot", fake_one_shot)
    monkeypatch.setattr(session_summarizer.handoff_curator, "mark_stale", fake_mark_stale)

    ok = await session_summarizer.summarize_one(session_id, workspace_id, "session-1")

    row = await pool.fetchrow(
        "SELECT status, summary, summary_model, summary_input_tokens, summary_output_tokens "
        "FROM sessions WHERE id = $1",
        session_id,
    )
    assert ok is True
    assert statuses_seen_by_llm == ["summarizing"]
    assert row["status"] == "ready"
    assert row["summary"] == "Implemented auth fix."
    assert row["summary_model"] == "claude-test-fast"
    assert row["summary_input_tokens"] == 11
    assert row["summary_output_tokens"] == 5
    assert stale_workspaces == [workspace_id]
