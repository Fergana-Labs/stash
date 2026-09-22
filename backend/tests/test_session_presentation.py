"""Recorded sessions name the actual work and the actual recording harness."""

import json
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from backend.config import settings
from backend.services import session_service, session_title_service
from backend.tasks import session_titles

from .test_permissions import _auth, _register


@pytest.mark.asyncio
async def test_recorded_client_survives_old_uploader_names(client, pool):
    key, user = await _register(client)
    owner = UUID(user["id"])
    response = await client.post(
        "/api/v1/me/sessions/events/batch",
        headers=_auth(key),
        json={
            "events": [
                {
                    "session_id": "continued",
                    "agent_name": user["name"],
                    "event_type": "user_message",
                    "content": "continue",
                    "metadata": {"client": "codex_cli", "model": "gpt-6-astra"},
                }
            ]
        },
    )
    assert response.status_code == 201
    # A delayed hook/transcript upload must not overwrite the known harness.
    await session_service.upsert_session(owner, "continued", agent_name=user["name"])
    response = await client.get("/api/v1/me/sessions", headers=_auth(key))
    assert response.json()["sessions"][0]["agent_name"] == "Codex"


@pytest.mark.asyncio
async def test_title_uses_opening_and_recent_conversation_not_tool_noise(client, pool, monkeypatch):
    _, user = await _register(client)
    owner = UUID(user["id"])
    await session_service.upsert_session(owner, "work", agent_name="Codex")
    for i in range(50):
        kind, content = (
            ("user_message", "continue") if i == 0 else ("tool_result", "large irrelevant log")
        )
        if i == 49:
            kind, content = (
                "assistant_message",
                "Fixed token pricing and isolated Heavi customer wikis.",
            )
        await pool.execute(
            "INSERT INTO history_events(owner_user_id,created_by,session_id,agent_name,event_type,content) VALUES($1,$1,'work','Codex',$2,$3)",
            owner,
            kind,
            content,
        )
    source = session_titles._source_text(await session_titles._session_events(owner, "work"))
    assert "continue" in source
    assert "Fixed token pricing" in source
    assert "irrelevant log" not in source
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "local")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    generate = AsyncMock(return_value="Fix pricing and preserve Heavi wikis")
    monkeypatch.setattr(session_titles, "_generate_title", generate)
    assert await session_titles._generate_for_session(owner, "work") == "generated"
    assert await session_titles._generate_for_session(owner, "work") == "fresh"
    generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_title_completion_is_not_an_agent_session(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "local")
    proc = AsyncMock()
    proc.returncode = 0
    proc.communicate.return_value = (
        json.dumps({"is_error": False, "result": "Fix token pricing"}).encode(),
        b"",
    )
    spawn = AsyncMock(return_value=proc)
    monkeypatch.setattr(session_titles.asyncio, "create_subprocess_exec", spawn)
    assert await session_titles._generate_title("some transcript") == "Fix token pricing"
    args = spawn.call_args.args
    assert args[args.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in args
    assert "--no-session-persistence" in args
    assert json.loads(args[args.index("--settings") + 1])["disableAllHooks"]


def test_local_titles_are_enqueued_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "local")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    calls = []
    monkeypatch.setattr(
        session_titles.generate_session_title, "delay", lambda *args: calls.append(args)
    )
    owner = UUID(int=1)
    session_title_service._enqueue_title_generation(owner, ["continued"])
    assert calls == [(str(owner), "continued")]


@pytest.mark.asyncio
async def test_agent_name_migration_repairs_existing_recordings(pool):
    import importlib
    import os

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    migration = importlib.import_module(
        "backend.migrations.versions.0227_recorded_session_agent_names"
    )
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        conn.execute(
            text("CREATE TEMP TABLE sessions(owner_user_id int,session_id text,agent_name text)")
        )
        conn.execute(
            text(
                "CREATE TEMP TABLE history_events(id int,owner_user_id int,session_id text,metadata jsonb,created_at timestamptz)"
            )
        )
        conn.execute(text("SET LOCAL search_path TO pg_temp,public"))
        conn.execute(
            text(
                "INSERT INTO sessions VALUES(1,'recorded','henry'),(1,'api','Heavi agent'),(2,'recorded','Another agent')"
            )
        )
        conn.execute(
            text("INSERT INTO history_events VALUES(1,1,'recorded',:metadata,now())"),
            {"metadata": json.dumps({"client": "codex_cli"})},
        )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert conn.execute(
            text("SELECT agent_name FROM sessions ORDER BY owner_user_id,session_id")
        ).scalars().all() == ["Heavi agent", "Codex", "Another agent"]

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()


def test_title_budget_keeps_the_last_sampled_message():
    events = [
        {"event_type": "assistant_message", "tool_name": None, "content": "x" * 1000}
        for _ in range(23)
    ]
    events.append(
        {"event_type": "assistant_message", "tool_name": None, "content": "FINAL_OUTCOME"}
    )
    assert "FINAL_OUTCOME" in session_titles._source_text(events)
