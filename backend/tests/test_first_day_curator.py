"""The first-day curator: during a workspace's first 24 hours the external
wiki updates after every conversation, not just on the nightly tick — a
developer who just activated the platform watches the wiki grow while they
integrate. The behavior that matters: it only fires for young developer
workspaces, it debounces so an event stream doesn't stack runs, and personal
scopes are untouched.
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
    monkeypatch.setattr(run_curator_now, "delay", lambda *a, **k: calls.append(a))
    return calls


async def _workspace_with_conversation(client: AsyncClient) -> UUID:
    api_key, _, workspace = await _developer(client)
    ws_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(client, ws_key, [_event("s-1", user_id="cust-1", user_name="Cust")])
    return UUID(workspace["scope_user_id"])


@pytest.mark.asyncio
async def test_first_day_conversation_dispatches_a_run(client: AsyncClient, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await _first_day_curator_tick(scope_id)
    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_old_workspace_does_not_dispatch(client: AsyncClient, pool, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await pool.execute(
        "UPDATE workspaces SET created_at = now() - interval '2 days' WHERE scope_user_id = $1",
        scope_id,
    )
    await _first_day_curator_tick(scope_id)
    assert dispatched == []


@pytest.mark.asyncio
async def test_recent_run_debounces(client: AsyncClient, pool, dispatched):
    scope_id = await _workspace_with_conversation(client)
    await pool.execute(
        "UPDATE agents SET last_run_outcome = 'ran', last_run_at = now() "
        "WHERE user_id = $1 AND is_curator AND curator_wiki = 'external'",
        scope_id,
    )
    await _first_day_curator_tick(scope_id)
    assert dispatched == []

    # Once the debounce window has passed, pending changes dispatch again.
    await pool.execute(
        "UPDATE agents SET last_run_at = $2 "
        "WHERE user_id = $1 AND is_curator AND curator_wiki = 'external'",
        scope_id,
        datetime.now(UTC) - timedelta(minutes=11),
    )
    await _first_day_curator_tick(scope_id)
    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_personal_scope_never_dispatches(client: AsyncClient, dispatched):
    _, body = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    await _first_day_curator_tick(UUID(body["id"]))
    assert dispatched == []
