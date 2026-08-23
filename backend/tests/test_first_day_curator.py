"""The first-day curator: during a scope's first 24 hours the wiki updates
after every conversation, not just on the nightly tick — a user who just
signed up (or a developer who just activated the platform) watches the wiki
grow while they get set up. The behavior that matters: it only fires for
young scopes, it debounces so an event stream doesn't stack runs, and it
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
    calls: list[tuple] = []
    monkeypatch.setattr(run_curator_now, "delay", lambda *a, **k: calls.append((a, k)))
    return calls


async def _workspace_with_conversation(client: AsyncClient) -> UUID:
    api_key, _, workspace = await _developer(client)
    ws_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(client, ws_key, [_event("s-1", user_id="cust-1", user_name="Cust")])
    return UUID(workspace["scope_user_id"])


async def _dispatched_wikis(pool, dispatched) -> set[str]:
    wikis = set()
    for args, _ in dispatched:
        wikis.add(
            await pool.fetchval("SELECT curator_wiki FROM agents WHERE id = $1", UUID(args[0]))
        )
    return wikis


@pytest.mark.asyncio
async def test_first_day_conversation_dispatches_unmetered_runs(
    client: AsyncClient, pool, dispatched
):
    scope_id = await _workspace_with_conversation(client)
    await _first_day_curator_tick(scope_id)
    # Both of the workspace's wikis update eagerly on day one: its own Memory
    # wiki and the cross-user external wiki.
    assert await _dispatched_wikis(pool, dispatched) == {"internal", "external"}
    # The platform is the trigger, so the runs must not eat the workspace's
    # free monthly curator allowance.
    assert all(kwargs == {"metered": False} for _, kwargs in dispatched)


@pytest.mark.asyncio
async def test_old_workspace_still_curates_its_own_memory(client: AsyncClient, pool, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await pool.execute(
        "UPDATE workspaces SET created_at = now() - interval '2 days' WHERE scope_user_id = $1",
        scope_id,
    )
    # The external wiki's first day is over; the scope user itself is still
    # fresh, so its own Memory wiki keeps updating eagerly.
    await _first_day_curator_tick(scope_id)
    assert await _dispatched_wikis(pool, dispatched) == {"internal"}


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
    assert await _dispatched_wikis(pool, dispatched) == {"internal", "external"}


async def _personal_user_with_conversation(client: AsyncClient) -> UUID:
    api_key, body = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "claude-code",
            "event_type": "assistant_message",
            "content": "hello",
            "session_id": "s-personal-1",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201
    return UUID(body["id"])


@pytest.mark.asyncio
async def test_personal_first_day_conversation_dispatches_an_unmetered_run(
    client: AsyncClient, pool, dispatched
):
    user_id = await _personal_user_with_conversation(client)
    await _first_day_curator_tick(user_id)
    assert await _dispatched_wikis(pool, dispatched) == {"internal"}
    assert dispatched[0][1] == {"metered": False}


@pytest.mark.asyncio
async def test_old_personal_account_does_not_dispatch(client: AsyncClient, pool, dispatched):
    user_id = await _personal_user_with_conversation(client)
    await pool.execute(
        "UPDATE users SET created_at = now() - interval '2 days' WHERE id = $1", user_id
    )
    await _first_day_curator_tick(user_id)
    assert dispatched == []


@pytest.mark.asyncio
async def test_personal_scope_with_nothing_new_does_not_dispatch(client: AsyncClient, dispatched):
    _, body = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    await _first_day_curator_tick(UUID(body["id"]))
    assert dispatched == []
