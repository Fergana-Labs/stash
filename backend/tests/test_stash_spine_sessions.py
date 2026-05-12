from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.routers import stashes
from backend.services import session_title_service


def test_session_title_json_text_accepts_fenced_json():
    text = '```json\n[{"session_id": "s1", "title": "Fix Auth"}]\n```'

    assert session_title_service._json_text(text) == '[{"session_id": "s1", "title": "Fix Auth"}]'


@pytest.mark.asyncio
async def test_session_titles_use_session_ids_when_generation_is_not_configured(monkeypatch):
    workspace_id = uuid4()
    last_at = datetime(2026, 5, 11, tzinfo=UTC)

    class Pool:
        async def fetch(self, *args):
            return []

        async def executemany(self, *args):
            raise AssertionError("placeholder titles should not be cached")

    async def generate_titles(candidates):
        raise AssertionError("generation should not run without an Anthropic key")

    monkeypatch.setattr(session_title_service, "get_pool", lambda: Pool())
    monkeypatch.setattr(session_title_service.settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(session_title_service, "_generate_titles", generate_titles)

    titles = await session_title_service.ensure_session_titles(
        workspace_id,
        [
            {
                "session_id": "agent-123",
                "agent_name": "codex",
                "event_count": 9,
                "size_bytes": 2048,
                "last_at": last_at,
                "stash_summary": "",
            }
        ],
    )

    assert titles == {"agent-123": "agent-123"}


@pytest.mark.asyncio
async def test_spine_sessions_use_generated_titles(monkeypatch):
    workspace_id = uuid4()

    async def list_workspace_sessions(stash_id):
        assert stash_id == workspace_id
        return [
            {
                "session_id": "agent-123",
                "agent_name": "codex",
                "event_count": 9,
                "size_bytes": 2048,
                "last_at": datetime(2026, 5, 11, tzinfo=UTC),
            }
        ]

    async def ensure_session_titles(stash_id, sessions):
        assert stash_id == workspace_id
        assert sessions[0]["session_id"] == "agent-123"
        return {"agent-123": "Add scrollable session list"}

    monkeypatch.setattr(stashes.memory_service, "list_workspace_sessions", list_workspace_sessions)
    monkeypatch.setattr(
        stashes.session_title_service, "ensure_session_titles", ensure_session_titles
    )

    sessions = await stashes._spine_sessions(workspace_id)

    assert sessions[0]["title"] == "Add scrollable session list"
    assert sessions[0]["event_count"] == 9
    assert sessions[0]["session_id"] == "agent-123"
