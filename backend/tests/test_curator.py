"""The daily Memory curator: provisioning, change feed, cost gate, prompt."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import agent_service, curation_service, prompts

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("cur"), "password": "securepassword1"},
    )
    return r.json()["api_key"], UUID(r.json()["id"])


def _auth(k: str) -> dict:
    return {"Authorization": f"Bearer {k}"}


@pytest.mark.asyncio
async def test_curator_provisioned_reserved_and_due(client: AsyncClient, _db_pool):
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    assert curator["is_curator"] and curator["run_mode"] == "scheduled"
    assert curator["schedule_cron"] and curator["schedule_prompt"] is None
    # Seeded baseline + watermark (backfill), so the cron can become due and
    # the first run bootstraps from real history — not NULL.
    assert curator["last_run_at"] is not None
    assert curator["curated_through"] is not None
    # Idempotent — same row on second call.
    again = await agent_service.get_or_create_curator(uid)
    assert again["id"] == curator["id"]


@pytest.mark.asyncio
async def test_curator_cannot_be_deleted(client: AsyncClient):
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    r = await client.delete(f"/api/v1/me/agents/{curator['id']}", headers=_auth(key))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_curator_provisioned_at_signup(client: AsyncClient):
    """Every account gets sleep-time curation from day one — including
    API-key-only production integrations that never touch chat or channels."""
    key, uid = await _register(client)
    agents = (await client.get("/api/v1/me/agents", headers=_auth(key))).json()["agents"]
    assert any(a["is_curator"] for a in agents)


@pytest.mark.asyncio
async def test_has_changes_and_feed_exclude_memory(client: AsyncClient, _db_pool):
    key, uid = await _register(client)
    old = datetime(2020, 1, 1, tzinfo=UTC)

    # A page in Files counts as a change.
    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Notes", "content": "a real note"},
        headers=_auth(key),
    )
    assert await curation_service.has_changes_since(uid, uid, old) is True

    feed = await curation_service.changes_since(uid, uid, old)
    assert any(p["name"] == "Notes" for p in feed["pages"])

    # A page written INTO the Memory folder must NOT appear (no self-curation).
    mem = (await client.get("/api/v1/me/memory-folder", headers=_auth(key))).json()
    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Wiki Page", "content": "curated", "folder_id": mem["id"]},
        headers=_auth(key),
    )
    feed2 = await curation_service.changes_since(uid, uid, old)
    assert all(p["name"] != "Wiki Page" for p in feed2["pages"])


@pytest.mark.asyncio
async def test_has_changes_false_after_watermark(client: AsyncClient, _db_pool):
    key, uid = await _register(client)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "P", "content": "x"}, headers=_auth(key)
    )
    future = datetime.now(UTC) + timedelta(hours=1)
    # Nothing changed after a future watermark → no changes → curator skipped.
    assert await curation_service.has_changes_since(uid, uid, future) is False


@pytest.mark.asyncio
async def test_changes_endpoint(client: AsyncClient):
    key, uid = await _register(client)
    r = await client.get("/api/v1/me/changes?since=2020-01-01T00:00:00", headers=_auth(key))
    assert r.status_code == 200
    body = r.json()
    assert "counts" in body and "history" in body and "pages" in body


def test_curator_prompt_embeds_folder_and_window():
    boot = prompts.render_curator_prompt("folder-123", None)
    assert "folder-123" in boot and "bootstrap" in boot.lower()
    # No dangling `--since` (it would swallow the next flag as its value).
    assert "stash changes --json" in boot and "--since" not in boot
    maint = prompts.render_curator_prompt("folder-123", "2026-07-06T09:00:00")
    assert "2026-07-06T09:00:00" in maint and "stash changes --since" in maint
    # The onboarding promise is upload → recompute → see it in the wiki: the
    # prompt must make uploads first-class content and forbid silent drops
    # (a bootstrap run once ignored a fresh upload entirely).
    assert "content, not context" in boot
    assert "never a silent drop" in boot
    # Links must be real markdown routes — double-bracket wiki syntax renders
    # as plain text in the product, so the prompt must never ask for it.
    assert "](/p/" in boot
    assert "[[" not in boot


async def _make_due(pool, agent_id: str, watermark: datetime) -> None:
    """Every-minute cron with a consumed-tick baseline in the past (due now),
    and the delta watermark set independently."""
    await pool.execute(
        "UPDATE agents SET schedule_cron = '* * * * *', "
        "last_run_at = now() - interval '5 minutes', curated_through = $2 "
        "WHERE id = $1",
        UUID(agent_id),
        watermark,
    )


@pytest.mark.asyncio
async def test_idle_curator_skipped_by_beat(client: AsyncClient, sprite_exec, _db_pool):
    """A due curator with no changes since its watermark must not wake the
    sprite; the skip consumes the cron tick but preserves the watermark."""
    from backend.tasks.agent_schedules import _run_due

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    # Due now, but nothing changed since a future watermark.
    future = datetime.now(UTC) + timedelta(hours=1)
    await _make_due(_db_pool, curator["id"], future)

    await _run_due()

    row = await _db_pool.fetchrow(
        "SELECT last_run_at, curated_through FROM agents WHERE id = $1", UUID(curator["id"])
    )
    assert sprite_exec.calls == []  # no sprite wake
    assert row["curated_through"] == future  # watermark preserved
    # Tick consumed — the next beat won't re-check until the next cron tick.
    assert row["last_run_at"] > datetime.now(UTC) - timedelta(minutes=1)


@pytest.mark.asyncio
async def test_curator_run_does_not_echo_loop(client: AsyncClient, sprite_exec, _db_pool):
    """A curator run writes its own transcript into history_events; that must
    not count as new changes, or the daily gate would fire forever."""
    from backend.services import curation_service
    from backend.tasks.agent_schedules import _run_due

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )
    await _make_due(_db_pool, curator["id"], datetime.now(UTC) - timedelta(minutes=2))

    ran = await _run_due()
    assert ran == 1

    after = await _db_pool.fetchval(
        "SELECT curated_through FROM agents WHERE id = $1", UUID(curator["id"])
    )
    # Watermark advanced past the page change, and the run's own transcript
    # doesn't re-trigger the gate or appear in the feed.
    assert await curation_service.has_changes_since(uid, uid, after) is False
    feed = await curation_service.changes_since(uid, uid, after)
    assert all(not str(e["session_id"] or "").startswith("agent-curate-") for e in feed["history"])


@pytest.mark.asyncio
async def test_curator_run_keeps_full_toolset(client: AsyncClient, sprite_exec, _db_pool):
    """The curator is a trusted headless run — it must NOT inherit the
    untrusted-channel tool restrictions (it needs to write the wiki)."""
    from backend.tasks.agent_schedules import _run_due

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )
    await _make_due(_db_pool, curator["id"], datetime.now(UTC) - timedelta(minutes=2))

    await _run_due()

    curator_argv = [a for a in sprite_exec.calls if "Memory Wiki Curation" in " ".join(a)]
    assert curator_argv and "--disallowedTools" not in curator_argv[0]


@pytest.mark.asyncio
async def test_failed_curator_run_preserves_watermark(
    client: AsyncClient, sprite_exec, _db_pool, monkeypatch
):
    """A failed run consumes the cron tick but must not advance the watermark —
    the un-curated delta is re-covered on the next successful run."""
    from backend.services import sprite_agent_service
    from backend.tasks.agent_schedules import _run_due

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )
    watermark = datetime.now(UTC) - timedelta(minutes=2)
    await _make_due(_db_pool, curator["id"], watermark)

    async def boom(agent, stamp):
        raise RuntimeError("sprite exploded")

    monkeypatch.setattr(sprite_agent_service, "run_scheduled", boom)
    ran = await _run_due()
    assert ran == 0

    after = await _db_pool.fetchval(
        "SELECT curated_through FROM agents WHERE id = $1", UUID(curator["id"])
    )
    assert after == watermark  # delta window intact


@pytest.mark.asyncio
async def test_failed_run_records_error_and_refunds_credit(
    client: AsyncClient, sprite_exec, _db_pool, monkeypatch
):
    """A failed run must be visible (last_run_error) and must not eat the
    free monthly allowance — an infra outage would otherwise silently burn
    all credits."""
    from backend.services import sprite_agent_service
    from backend.tasks.agent_schedules import _run_due

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )
    await _make_due(_db_pool, curator["id"], datetime.now(UTC) - timedelta(minutes=2))

    async def boom(agent, stamp):
        raise RuntimeError("sprite exploded")

    real_run_scheduled = sprite_agent_service.run_scheduled
    monkeypatch.setattr(sprite_agent_service, "run_scheduled", boom)
    await _run_due()

    row = await _db_pool.fetchrow(
        "SELECT last_run_error, month_run_count FROM agents WHERE id = $1",
        UUID(curator["id"]),
    )
    assert "sprite exploded" in row["last_run_error"]
    assert row["month_run_count"] == 0  # consumed by mark_run, refunded on failure

    # The next successful run clears the error. Re-patch the real function
    # rather than monkeypatch.undo() — the fixture is shared with sprite_exec,
    # so undo() would also drop the fake sprite exec and this "successful run"
    # would exec a real `claude` binary (passes on a dev machine, dies in CI).
    monkeypatch.setattr(sprite_agent_service, "run_scheduled", real_run_scheduled)
    await _make_due(_db_pool, curator["id"], datetime.now(UTC) - timedelta(minutes=2))
    ran = await _run_due()
    assert ran == 1
    row = await _db_pool.fetchrow(
        "SELECT last_run_error, month_run_count FROM agents WHERE id = $1",
        UUID(curator["id"]),
    )
    assert row["last_run_error"] is None
    assert row["month_run_count"] == 1


# --- Manual recompute (POST /me/memory/recompute) ---


@pytest.mark.asyncio
async def test_recompute_runs_curator_now(client: AsyncClient, sprite_exec, _db_pool):
    """The onboarding flow: upload documents, recompute, watch the wiki build —
    no waiting for the daily tick. The run advances the watermark."""
    from backend.tasks.agent_schedules import _run_curator_now, run_curator_now

    key, uid = await _register(client)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )

    started = []
    run_curator_now.delay = lambda agent_id: started.append(agent_id)
    r = await client.post("/api/v1/me/memory/recompute", headers=_auth(key))
    assert r.status_code == 202
    curator = await agent_service.get_or_create_curator(uid)
    assert started == [curator["id"]]

    before = datetime.now(UTC)
    await _run_curator_now(UUID(curator["id"]))
    row = await _db_pool.fetchrow(
        "SELECT curated_through, last_run_at FROM agents WHERE id = $1", UUID(curator["id"])
    )
    assert sprite_exec.calls  # the run actually woke the sprite
    assert row["curated_through"] >= before - timedelta(seconds=5)

    # The run's events carry the curator's own name, so its sessions are
    # attributable in the Agents/Sessions lists (not generic "Stash Agent").
    names = await _db_pool.fetch(
        "SELECT DISTINCT agent_name FROM history_events WHERE session_id LIKE 'agent-curate-%'"
    )
    assert [n["agent_name"] for n in names] == ["Memory curator"]


@pytest.mark.asyncio
async def test_failed_manual_recompute_records_error(
    client: AsyncClient, sprite_exec, _db_pool, monkeypatch
):
    """The recompute endpoint answers 202 before the worker runs, so the
    agent row is the only place a crash can surface."""
    from backend.services import sprite_agent_service
    from backend.tasks.agent_schedules import _run_curator_now

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)

    async def boom(agent, stamp):
        raise RuntimeError("harness missing")

    monkeypatch.setattr(sprite_agent_service, "run_scheduled", boom)
    with pytest.raises(RuntimeError):
        await _run_curator_now(UUID(curator["id"]))

    row = await _db_pool.fetchrow(
        "SELECT last_run_error, month_run_count FROM agents WHERE id = $1",
        UUID(curator["id"]),
    )
    assert "harness missing" in row["last_run_error"]
    assert row["month_run_count"] == 0

    # The error is visible through the API the CLI reads.
    r = await client.get("/api/v1/me/agents", headers=_auth(key))
    fetched = next(a for a in r.json()["agents"] if a["is_curator"])
    assert fetched["last_run_error"] == "harness missing"


@pytest.mark.asyncio
async def test_recompute_409_when_nothing_changed(client: AsyncClient, _db_pool):
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    future = datetime.now(UTC) + timedelta(hours=1)
    await _db_pool.execute(
        "UPDATE agents SET curated_through = $2 WHERE id = $1", UUID(curator["id"]), future
    )
    r = await client.post("/api/v1/me/memory/recompute", headers=_auth(key))
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_recompute_metered_like_the_scheduler(client: AsyncClient, _db_pool):
    """Manual runs draw from the same monthly sleep-time allowance: free
    accounts stop at the cap, enterprise is unlimited."""
    from backend.config import settings
    from backend.tasks.agent_schedules import run_curator_now

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )
    await _db_pool.execute(
        "UPDATE agents SET month_run_count = $2, "
        "month_run_anchor = date_trunc('month', now())::date WHERE id = $1",
        UUID(curator["id"]),
        settings.FREE_CURATOR_RUNS_PER_MONTH,
    )

    r = await client.post("/api/v1/me/memory/recompute", headers=_auth(key))
    assert r.status_code == 402

    await _db_pool.execute("UPDATE users SET plan = 'enterprise' WHERE id = $1", uid)
    run_curator_now.delay = lambda agent_id: None
    r = await client.post("/api/v1/me/memory/recompute", headers=_auth(key))
    assert r.status_code == 202


# --- Memory wiki graph (GET /me/memory-graph) ---


@pytest.mark.asyncio
async def test_memory_graph_nodes_edges_and_scope(client: AsyncClient):
    key, uid = await _register(client)
    mem = (await client.get("/api/v1/me/memory-folder", headers=_auth(key))).json()

    async def add_page(name: str, content: str, folder_id: str | None) -> str:
        r = await client.post(
            "/api/v1/me/pages/new",
            json={"name": name, "content": content, "folder_id": folder_id},
            headers=_auth(key),
        )
        assert r.status_code == 201
        return r.json()["id"]

    alpha = await add_page("Alpha", "seed page", mem["id"])
    beta = await add_page("Beta", f"see [Alpha](/p/{alpha})", mem["id"])
    # A Files page linking into the wiki is not a wiki node and adds no edge.
    await add_page("Outside", f"see [Alpha](/p/{alpha})", None)

    r = await client.get("/api/v1/me/memory-graph", headers=_auth(key))
    assert r.status_code == 200
    graph = r.json()
    assert {n["name"] for n in graph["nodes"]} == {"Alpha", "Beta"}
    a, b = sorted([alpha, beta])
    assert graph["edges"] == [{"source": a, "target": b}]
    # The link is one undirected edge — both ends count it in their degree.
    assert {n["name"]: n["degree"] for n in graph["nodes"]} == {"Alpha": 1, "Beta": 1}


# --- Memory wiki file-system tree (GET /me/memory-tree) ---


@pytest.mark.asyncio
async def test_memory_tree_nests_folders_and_scopes_to_memory(client: AsyncClient):
    key, uid = await _register(client)
    mem = (await client.get("/api/v1/me/memory-folder", headers=_auth(key))).json()

    sub = (
        await client.post(
            "/api/v1/me/folders",
            json={"name": "Research", "parent_folder_id": mem["id"]},
            headers=_auth(key),
        )
    ).json()

    async def add_page(name: str, folder_id: str | None) -> str:
        r = await client.post(
            "/api/v1/me/pages/new",
            json={"name": name, "content": "x", "folder_id": folder_id},
            headers=_auth(key),
        )
        assert r.status_code == 201
        return r.json()["id"]

    root_page = await add_page("Index", mem["id"])
    nested_page = await add_page("Deep Dive", sub["id"])
    # A Files page is not part of the wiki tree.
    await add_page("Outside", None)

    r = await client.get("/api/v1/me/memory-tree", headers=_auth(key))
    assert r.status_code == 200
    tree = r.json()
    assert [p["id"] for p in tree["pages"]] == [root_page]
    assert [f["name"] for f in tree["folders"]] == ["Research"]
    assert [p["id"] for p in tree["folders"][0]["pages"]] == [nested_page]

    # The Files tree keeps hiding the Memory subtree — the two stay MECE.
    files_tree = (await client.get("/api/v1/me/tree", headers=_auth(key))).json()
    assert [p["name"] for p in files_tree["pages"]] == ["Outside"]
    assert all(f["id"] != mem["id"] for f in files_tree["folders"])
