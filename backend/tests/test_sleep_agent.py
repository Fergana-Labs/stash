"""Tests for sleep agent watermark advancement and advisory lock behaviour."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.services import sleep_service
from .conftest import unique_name


async def _make_persona(pool):
    """Create a minimal persona with provisioned history + notebook."""
    api_key_hash = "hash_" + uuid.uuid4().hex
    name = unique_name("persona")
    user = await pool.fetchrow(
        "INSERT INTO users (name, type, api_key_hash) VALUES ($1, 'persona', $2) RETURNING id",
        name, api_key_hash,
    )
    persona_id = user["id"]

    history = await pool.fetchrow(
        "INSERT INTO histories (name, created_by) VALUES ('hist', $1) RETURNING id",
        persona_id,
    )
    notebook = await pool.fetchrow(
        "INSERT INTO notebooks (name, created_by) VALUES ('nb', $1) RETURNING id",
        persona_id,
    )
    await pool.execute(
        "UPDATE users SET history_id = $1, notebook_id = $2 WHERE id = $3",
        history["id"], notebook["id"], persona_id,
    )
    return persona_id, history["id"], notebook["id"]


@pytest.mark.asyncio
async def test_curate_returns_no_new_data_when_empty(pool):
    """curate() should return no_new_data when the history store is empty."""
    persona_id, _, _ = await _make_persona(pool)
    result = await sleep_service.curate(persona_id)
    assert result["status"] == "no_new_data"


@pytest.mark.asyncio
async def test_advisory_lock_prevents_double_run(pool):
    """A second concurrent curate() call must return 'locked' while the first holds the lock."""
    persona_id, _, _ = await _make_persona(pool)
    lock_key = int(persona_id) & 0x7FFFFFFFFFFFFFFF

    # Manually acquire the advisory lock to simulate another process holding it
    conn = await pool.acquire()
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", lock_key)
        result = await sleep_service.curate(persona_id)
        assert result["status"] == "locked"
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", lock_key)
        await pool.release(conn)


@pytest.mark.asyncio
async def test_watermark_advances_after_events(pool):
    """After injecting events, the watermark last_event_at should be set."""
    persona_id, history_id, _ = await _make_persona(pool)

    # Push a synthetic event directly into history
    await pool.execute(
        "INSERT INTO history_events (store_id, agent_name, event_type, content) "
        "VALUES ($1, 'test_agent', 'tool_use', 'did something')",
        history_id,
    )

    # Patch the LLM call so we don't need real Anthropic credentials
    mock_result = {
        "create_notes": [],
        "update_notes": [],
        "merge_notes": [],
        "delete_notes": [],
        "update_categories": [],
        "health": {},
    }
    with patch("backend.services.sleep_service._llm_curate", new=AsyncMock(return_value=mock_result)):
        with patch("backend.services.sleep_service._generate_monologue_text", new=AsyncMock(return_value="")):
            result = await sleep_service.curate(persona_id)

    assert result["status"] in ("completed", "no_new_data")

    # Verify watermark was written
    wm = await pool.fetchrow(
        "SELECT last_event_at FROM sleep_watermarks WHERE persona_id = $1", persona_id
    )
    assert wm is not None
    assert wm["last_event_at"] is not None


@pytest.mark.asyncio
async def test_get_due_agents_excludes_disabled(pool):
    """Persona with enabled=false in sleep_configs must not appear in due agents."""
    persona_id, _, _ = await _make_persona(pool)
    await pool.execute(
        "INSERT INTO sleep_configs (persona_id, enabled) VALUES ($1, false)", persona_id,
    )
    due = await sleep_service.get_due_agents()
    assert persona_id not in due
