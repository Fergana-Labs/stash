"""Tests for the stash handoff writer service + worker query.

Avoids real LLM calls — focuses on mark_stale upsert behavior, fingerprint
stability, the daily-cadence worker query, and the pin/unpin state machine.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import handoff_writer, prompts


@pytest_asyncio.fixture
async def workspace(_db_pool):
    user_id = uuid4()
    ws_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name) VALUES ($1, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    await _db_pool.execute(
        "INSERT INTO workspaces (id, name, creator_id, invite_code) " "VALUES ($1, $2, $3, $4)",
        ws_id,
        f"ws_{ws_id.hex[:6]}",
        user_id,
        ws_id.hex[:12],
    )
    return {"id": ws_id, "owner_id": user_id}


@pytest.mark.asyncio
async def test_mark_stale_creates_row_then_idempotent(workspace, _db_pool):
    ws = workspace["id"]
    await handoff_writer.mark_stale(ws)
    row = await _db_pool.fetchrow(
        "SELECT stale, stale_marked_at FROM stash_handoffs WHERE workspace_id = $1", ws
    )
    assert row is not None
    assert row["stale"] is True
    first_marked = row["stale_marked_at"]
    assert first_marked is not None

    # Calling again should not move the marker forward (preserves the
    # "earliest dirty since" semantics that the worker's QUIET_PERIOD relies on).
    await handoff_writer.mark_stale(ws)
    row2 = await _db_pool.fetchrow(
        "SELECT stale, stale_marked_at FROM stash_handoffs WHERE workspace_id = $1", ws
    )
    assert row2["stale"] is True
    assert row2["stale_marked_at"] == first_marked


@pytest.mark.asyncio
async def test_fingerprint_stable_under_session_reordering():
    seed_a = prompts.HandoffSeed(
        workspace_name="x",
        description=None,
        sessions=[
            {"session_id": "s1", "agent_name": "a", "last_at": "2026-05-01", "summary": "one"},
            {"session_id": "s2", "agent_name": "b", "last_at": "2026-05-02", "summary": "two"},
        ],
        pages=[],
        file_counts={},
        recent_files=[],
        activity=[],
    )
    seed_b = prompts.HandoffSeed(
        workspace_name="x",
        description=None,
        sessions=list(reversed(seed_a.sessions)),
        pages=[],
        file_counts={},
        recent_files=[],
        activity=[],
    )
    assert handoff_writer._seed_fingerprint(seed_a) == handoff_writer._seed_fingerprint(seed_b)


@pytest.mark.asyncio
async def test_fingerprint_changes_when_description_changes():
    seed = prompts.HandoffSeed(
        workspace_name="x",
        description="be concise",
        sessions=[],
        pages=[],
        file_counts={},
        recent_files=[],
        activity=[],
    )
    fp1 = handoff_writer._seed_fingerprint(seed)
    seed.description = "be concise. cite files."
    fp2 = handoff_writer._seed_fingerprint(seed)
    assert fp1 != fp2


@pytest.mark.asyncio
async def test_edit_pins_and_excludes_from_worker_query(workspace, _db_pool):
    ws = workspace["id"]
    user = workspace["owner_id"]

    await handoff_writer.mark_stale(ws)
    await handoff_writer.edit_and_pin(ws, "pinned body", user)

    row = await _db_pool.fetchrow(
        "SELECT body_markdown, pinned_at, pinned_by, stale "
        "FROM stash_handoffs WHERE workspace_id = $1",
        ws,
    )
    assert row["body_markdown"] == "pinned body"
    assert row["pinned_at"] is not None
    assert row["pinned_by"] == user
    assert row["stale"] is False

    # Worker query (mirrors backend/workers/handoff_writer.py) — should NOT
    # find this row because pinned_at is set, even after we mark it stale.
    await handoff_writer.mark_stale(ws)  # would normally re-eligible
    eligible = await _db_pool.fetch(
        """
        SELECT workspace_id FROM stash_handoffs
        WHERE stale = TRUE
          AND pinned_at IS NULL
          AND stale_marked_at <= now() - $1::interval
          AND (generated_at IS NULL OR generated_at <= now() - $2::interval)
        """,
        timedelta(seconds=0),
        timedelta(hours=24),
    )
    assert all(r["workspace_id"] != ws for r in eligible)


@pytest.mark.asyncio
async def test_unpin_clears_pin_and_resets_generated_at(workspace, _db_pool):
    ws = workspace["id"]
    user = workspace["owner_id"]
    await handoff_writer.edit_and_pin(ws, "pinned", user)
    # Pretend the worker had run before we pinned
    await _db_pool.execute(
        "UPDATE stash_handoffs SET generated_at = now() WHERE workspace_id = $1", ws
    )

    await handoff_writer.unpin(ws)

    row = await _db_pool.fetchrow(
        "SELECT body_markdown, pinned_at, pinned_by, stale, generated_at "
        "FROM stash_handoffs WHERE workspace_id = $1",
        ws,
    )
    assert row["pinned_at"] is None
    assert row["pinned_by"] is None
    assert row["stale"] is True
    assert row["generated_at"] is None  # forces worker bypass of 24h gap
    assert row["body_markdown"] == "pinned"  # body preserved until next regen


@pytest.mark.asyncio
async def test_24h_gap_prevents_immediate_re_regen(workspace, _db_pool):
    """A stash that just regenerated stays out of the worker query for ~24h."""
    ws = workspace["id"]
    await _db_pool.execute(
        """
        INSERT INTO stash_handoffs (workspace_id, body_markdown, generated_at, stale, stale_marked_at)
        VALUES ($1, 'doc', now() - INTERVAL '1 hour', TRUE, now() - INTERVAL '10 minutes')
        """,
        ws,
    )

    eligible = await _db_pool.fetch(
        """
        SELECT workspace_id FROM stash_handoffs
        WHERE stale = TRUE
          AND pinned_at IS NULL
          AND stale_marked_at <= now() - $1::interval
          AND (generated_at IS NULL OR generated_at <= now() - $2::interval)
        """,
        timedelta(minutes=5),
        timedelta(hours=24),
    )
    assert all(
        r["workspace_id"] != ws for r in eligible
    ), "regen-within-24h should not be picked up by the daily worker"


@pytest.mark.asyncio
async def test_seed_gather_handles_empty_workspace(workspace):
    """A brand-new stash with no sessions/pages/files should produce a valid
    seed — the prompt instructs the agent to handle the empty case
    explicitly."""
    seed = await handoff_writer._gather_seed(workspace["id"])
    assert seed.sessions == []
    assert seed.pages == []
    assert seed.file_counts == {}
    assert seed.recent_files == []
    assert seed.activity == []
    # Description column is empty by default on the test workspace.
    assert seed.description in (None, "")
    # Render must succeed even on empty input.
    text = prompts.render_handoff_seed(seed)
    assert "(none yet)" in text


@pytest.mark.asyncio
async def test_seed_no_longer_reads_handoff_principles_page(workspace, _db_pool):
    """We dropped the HANDOFF_PRINCIPLES.md verbatim-include path. A page
    with that name should NOT end up in the seed — workspaces.description
    is the canonical human-written input now."""
    ws = workspace["id"]
    user = workspace["owner_id"]
    await _db_pool.execute(
        "INSERT INTO pages (workspace_id, name, content_markdown, created_by, updated_by) "
        "VALUES ($1, 'HANDOFF_PRINCIPLES.md', 'do not include me', $2, $2)",
        ws,
        user,
    )
    seed = await handoff_writer._gather_seed(ws)
    rendered = prompts.render_handoff_seed(seed)
    assert "do not include me" not in rendered
    assert not hasattr(seed, "principles_body")
