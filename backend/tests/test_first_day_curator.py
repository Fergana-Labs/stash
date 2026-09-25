"""The first-day curator: personal onboarding runs after five useful traces;
developer workspaces still update eagerly while being configured. It only
fires for young scopes, debounces so an event stream doesn't stack runs, and
never fires with nothing new to curate.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.tasks.agent_schedules import _first_day_curator_tick, run_curator_now

from .conftest import unique_name
from .test_developer_platform import _developer, _event, _mint_workspace_key, _push
from .test_permissions import _register_with_email


@pytest.fixture
def dispatched(monkeypatch):
    from backend.config import settings
    from backend.tasks.session_titles import generate_session_title

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setattr(generate_session_title, "delay", lambda *a, **k: None)
    calls: list[tuple] = []
    monkeypatch.setattr(run_curator_now, "delay", lambda *a, **k: calls.append((a, k)))
    return calls


async def _workspace_with_conversation(client: AsyncClient) -> UUID:
    api_key, _, workspace = await _developer(client)
    ws_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(client, ws_key, [_event("s-1", user_id="cust-1", user_name="Cust")])
    return UUID(workspace["scope_user_id"])


async def _dispatched_skills(pool, dispatched) -> set[str]:
    skills = set()
    for args, _ in dispatched:
        skills.add(
            await pool.fetchval("SELECT curator_skill FROM agents WHERE id = $1", UUID(args[0]))
        )
    return skills


@pytest.mark.asyncio
async def test_first_day_conversation_dispatches_runs(client: AsyncClient, pool, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await _first_day_curator_tick(scope_id)
    # Both of the workspace's skills update eagerly on day one: its own Memory
    # skill and the cross-user external skill.
    assert await _dispatched_skills(pool, dispatched) == {"internal", "external"}
    assert all(kwargs == {"automatic": True} for _, kwargs in dispatched)


@pytest.mark.asyncio
async def test_paused_curator_stays_paused_on_first_day(client, pool, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await pool.execute(
        "UPDATE agents SET run_mode='chat' WHERE user_id=$1 AND is_curator", scope_id
    )
    await _first_day_curator_tick(scope_id)
    assert dispatched == []


@pytest.mark.asyncio
async def test_old_workspace_still_curates_its_own_memory(client: AsyncClient, pool, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await pool.execute(
        "UPDATE workspaces SET created_at = now() - interval '2 days' WHERE scope_user_id = $1",
        scope_id,
    )
    # The external skill's first day is over; the scope user itself is still
    # fresh, so its own curated Skill keeps updating eagerly.
    await _first_day_curator_tick(scope_id)
    assert await _dispatched_skills(pool, dispatched) == {"internal"}


@pytest.mark.asyncio
async def test_old_scope_does_not_dispatch(client: AsyncClient, pool, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await pool.execute(
        "UPDATE workspaces SET created_at = now() - interval '2 days' WHERE scope_user_id = $1",
        scope_id,
    )
    await pool.execute(
        "UPDATE users SET created_at = now() - interval '2 days' WHERE id = $1", scope_id
    )
    await _first_day_curator_tick(scope_id)
    assert dispatched == []


@pytest.mark.asyncio
async def test_recent_run_debounces(client: AsyncClient, pool, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await pool.execute(
        "UPDATE agents SET last_run_outcome = 'ran', last_run_at = now() "
        "WHERE user_id = $1 AND is_curator",
        scope_id,
    )
    await _first_day_curator_tick(scope_id)
    assert dispatched == []

    # Once the debounce window has passed, pending changes dispatch again.
    await pool.execute(
        "UPDATE agents SET last_run_at = $2 WHERE user_id = $1 AND is_curator",
        scope_id,
        datetime.now(UTC) - timedelta(minutes=11),
    )
    await _first_day_curator_tick(scope_id)
    assert await _dispatched_skills(pool, dispatched) == {"internal", "external"}


async def _personal_user_with_conversations(client: AsyncClient, count: int = 1) -> UUID:
    api_key, body = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    for index in range(count):
        resp = await client.post(
            "/api/v1/me/sessions/events",
            json={
                "agent_name": "claude-code",
                "event_type": "assistant_message",
                "content": "hello",
                "session_id": f"s-personal-{index}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 201
    return UUID(body["id"])


@pytest.mark.asyncio
async def test_personal_curation_starts_with_one_session(client: AsyncClient, pool, dispatched):
    user_id = await _personal_user_with_conversations(client, 1)
    await _first_day_curator_tick(user_id)
    assert await _dispatched_skills(pool, dispatched) == {"internal"}


@pytest.mark.asyncio
async def test_personal_curation_accepts_multiple_sessions(client: AsyncClient, pool, dispatched):
    user_id = await _personal_user_with_conversations(client, 5)
    await _first_day_curator_tick(user_id)
    assert await _dispatched_skills(pool, dispatched) == {"internal"}
    assert dispatched[0][1] == {"automatic": True}


@pytest.mark.asyncio
async def test_old_personal_account_still_gets_its_first_skill_bootstrap(
    client: AsyncClient, pool, dispatched
):
    user_id = await _personal_user_with_conversations(client, 5)
    await pool.execute(
        "UPDATE users SET created_at = now() - interval '2 days' WHERE id = $1", user_id
    )
    await _first_day_curator_tick(user_id)
    assert await _dispatched_skills(pool, dispatched) == {"internal"}


@pytest.mark.asyncio
async def test_personal_scope_with_nothing_new_does_not_dispatch(client: AsyncClient, dispatched):
    _, body = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    await _first_day_curator_tick(UUID(body["id"]))
    assert dispatched == []


async def _push_historical_event(
    client: AsyncClient, api_key: str, created_at: datetime, session_id: str = "s-imported-1"
) -> None:
    resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "claude-code",
            "event_type": "assistant_message",
            "content": "an old conversation",
            "session_id": session_id,
            "created_at": created_at.isoformat(),
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_imported_pre_signup_history_dispatches(client: AsyncClient, pool, dispatched):
    """Imported sessions keep their original timestamps, which predate the
    curator's seeded curated_through. The import must pull curated_through
    back so the first-day run actually reads the history."""
    api_key, body = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    user_id = UUID(body["id"])
    old = datetime.now(UTC) - timedelta(days=10)
    for index in range(5):
        await _push_historical_event(client, api_key, old, f"s-imported-{index}")
    curated_through = await pool.fetchval(
        "SELECT curated_through FROM agents WHERE user_id = $1 AND is_curator", user_id
    )
    assert curated_through < old
    await _first_day_curator_tick(user_id)
    assert await _dispatched_skills(pool, dispatched) == {"internal"}


@pytest.mark.asyncio
async def test_late_import_reopens_curation(client: AsyncClient, pool, dispatched):
    """A curator that already ran has curated_through at its last run; an
    import of older sessions after that must still pull it back."""
    api_key, body = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    user_id = UUID(body["id"])
    await pool.execute(
        "UPDATE users SET created_at = now() - interval '2 days' WHERE id = $1", user_id
    )
    await pool.execute(
        "UPDATE agents SET last_run_outcome = 'ran', last_run_at = now(), curated_through = now() "
        "WHERE user_id = $1 AND is_curator",
        user_id,
    )
    old = datetime.now(UTC) - timedelta(days=10)
    await _push_historical_event(client, api_key, old)
    curated_through = await pool.fetchval(
        "SELECT curated_through FROM agents WHERE user_id = $1 AND is_curator", user_id
    )
    assert curated_through < old
    # Past the first day nothing dispatches immediately — the nightly run
    # picks the import up, because the pending-changes gate now sees it.
    await _first_day_curator_tick(user_id)
    assert dispatched == []
    from backend.services import curation_service

    assert await curation_service.has_changes_since(user_id, user_id, curated_through)


@pytest.mark.asyncio
async def test_queued_automatic_run_respects_schedule_disabled_after_dispatch(
    client, pool, sprite_exec
):
    from backend.services import agent_service
    from backend.tasks.agent_schedules import _run_curator_now

    _, _, workspace = await _developer(client)
    agent = await agent_service.get_or_create_curator(UUID(workspace["scope_user_id"]))
    await pool.execute("UPDATE agents SET run_mode='chat' WHERE id=$1", UUID(agent["id"]))
    await _run_curator_now(UUID(agent["id"]), automatic=True)
    assert sprite_exec.calls == []
