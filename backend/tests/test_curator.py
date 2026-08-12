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
async def test_curator_schedule_turns_off_and_back_on(client: AsyncClient, _db_pool):
    """The off switch for users who curate locally (e.g. Chainbase): run_mode
    'chat' takes the curator out of the beat's pickup so the nightly cloud run
    can't fire mid-work, while the watermark survives so nothing un-curated is
    lost when the schedule comes back on."""
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)

    r = await client.patch(
        f"/api/v1/me/agents/{curator['id']}", json={"run_mode": "chat"}, headers=_auth(key)
    )
    assert r.status_code == 200
    off = r.json()
    assert off["run_mode"] == "chat"
    # The cron baseline clears; the delta watermark stays.
    assert off["last_run_at"] is None
    assert datetime.fromisoformat(off["curated_through"]) == curator["curated_through"]
    assert curator["id"] not in {a["id"] for a in await agent_service.list_scheduled()}

    r = await client.patch(
        f"/api/v1/me/agents/{curator['id']}", json={"run_mode": "scheduled"}, headers=_auth(key)
    )
    assert r.status_code == 200
    on = r.json()
    assert on["run_mode"] == "scheduled"
    # Baseline re-seeds to now, so the schedule resumes at the next cron tick
    # rather than firing immediately for the paused window.
    assert on["last_run_at"] is not None
    assert curator["id"] in {a["id"] for a in await agent_service.list_scheduled()}


@pytest.mark.asyncio
async def test_curator_only_run_mode_is_editable(client: AsyncClient):
    """The curator is reserved: its staggered cron, name, and prompt are
    Stash-managed. A PATCH touching anything but run_mode is refused."""
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    r = await client.patch(
        f"/api/v1/me/agents/{curator['id']}",
        json={"schedule_cron": "0 9 * * *"},
        headers=_auth(key),
    )
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
async def test_hydrated_saves_flow_through_the_feed(client: AsyncClient, _db_pool):
    """An X/Instagram save is deliberate curation input like an upload, so a
    newly hydrated save must both trip the cheap gate and appear as an item
    in the delta — a still-pending skeleton row must do neither."""
    from backend.services import source_service

    key, uid = await _register(client)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    source = await source_service.create_source(
        owner_user_id=str(uid),
        source_type="x_saves",
        external_ref=unique_name("acct"),
        display_name="X",
    )
    await _db_pool.execute(
        "INSERT INTO x_save_docs (owner_user_id, source_id, path, name, kind, external_ref, "
        "content, hydration_status) "
        "VALUES ($1, $2, '77', '@bob - 77', 'Bookmark', '77', 'a saved thread', 'done'), "
        "       ($1, $2, '78', '78', 'Bookmark', '78', NULL, 'pending')",
        uid,
        UUID(source["id"]),
    )

    assert await curation_service.has_changes_since(uid, uid, old) is True
    feed = await curation_service.changes_since(uid, uid, old)
    assert feed["counts"]["saves"] == 1
    save = feed["saves"][0]
    assert save["name"] == "@bob - 77"
    assert save["url"] == "https://x.com/i/status/77"
    assert save["snippet"] == "a saved thread"


@pytest.mark.asyncio
async def test_changed_drive_docs_flow_through_the_feed(client: AsyncClient, _db_pool):
    """A doc edited in a connected Drive folder is curation input like an
    upload: once its new body is extracted it must trip the cheap gate and
    appear in the delta. A doc still mid-extraction or deleted must do
    neither — the curator only sees documents whose text is readable."""
    from backend.services import source_service

    key, uid = await _register(client)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    source = await source_service.create_source(
        owner_user_id=str(uid),
        source_type="google_drive_folder",
        external_ref=unique_name("folder"),
        display_name="Part Cheat Sheets",
    )
    await _db_pool.execute(
        "INSERT INTO drive_documents (owner_user_id, source_id, path, name, kind, "
        "external_ref, content, extraction_status, deleted_at) VALUES "
        "($1, $2, 'Sheets/Brakes', 'Brakes', 'file', 'g1', 'the final recipe', 'done', NULL), "
        "($1, $2, 'Sheets/Hubs', 'Hubs', 'file', 'g2', NULL, 'pending', NULL), "
        "($1, $2, 'Sheets/Old', 'Old', 'file', 'g3', 'stale', 'done', now())",
        uid,
        UUID(source["id"]),
    )

    assert await curation_service.has_changes_since(uid, uid, old) is True
    feed = await curation_service.changes_since(uid, uid, old)
    assert feed["counts"]["source_docs"] == 1
    doc = feed["source_docs"][0]
    assert doc["path"] == "Sheets/Brakes"
    assert doc["snippet"] == "the final recipe"


async def _push_events(client: AsyncClient, key: str, events: list[dict]) -> None:
    r = await client.post(
        "/api/v1/me/sessions/events/batch", json={"events": events}, headers=_auth(key)
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_feed_overflow_never_drops_events(client: AsyncClient, _db_pool, monkeypatch):
    """A busy account can produce more events than one delta holds. The feed
    truncates, but the watermark bound stops at the last event that fit — so
    the next run picks up exactly where this one left off, and every event is
    eventually curated."""
    monkeypatch.setattr(curation_service, "_MAX_EVENTS", 3)
    key, uid = await _register(client)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    await _push_events(
        client,
        key,
        [
            {
                "agent_name": "heavi-chat",
                "event_type": "user_message",
                "content": f"turn {i}",
                "session_id": f"conv-{i}",
                "created_at": (base + timedelta(minutes=i)).isoformat(),
            }
            for i in range(5)
        ],
    )

    feed = await curation_service.changes_since(uid, uid, old)
    assert feed["history_has_more"] is True
    assert [h["content"] for h in feed["history"]] == ["turn 0", "turn 1", "turn 2"]

    until = base + timedelta(hours=1)
    through = await curation_service.complete_through(uid, old, until)
    # Complete only through the last event that fit, not through `until`.
    assert through < base + timedelta(minutes=3)

    # The next run's feed starts where this one stopped: nothing was lost.
    # The boundary event re-appears by design — the watermark backs off a
    # microsecond so events sharing its timestamp can never be skipped; a
    # duplicated boundary event is the cheap side of that trade.
    next_feed = await curation_service.changes_since(uid, uid, through)
    assert [h["content"] for h in next_feed["history"]] == ["turn 2", "turn 3", "turn 4"]
    assert next_feed["history_has_more"] is False
    assert await curation_service.complete_through(uid, through, until) == until


@pytest.mark.asyncio
async def test_curate_sessions_do_not_consume_feed_slots(
    client: AsyncClient, _db_pool, monkeypatch
):
    """The curator's own run transcripts are excluded in SQL. If they were
    filtered after the query they would eat delta slots and could crowd real
    activity out of the feed entirely."""
    monkeypatch.setattr(curation_service, "_MAX_EVENTS", 3)
    key, uid = await _register(client)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    curate_noise = [
        {
            "agent_name": "curator",
            "event_type": "assistant_message",
            "content": f"curator step {i}",
            "session_id": "agent-curate-abc-202601011200",
            "created_at": (base + timedelta(seconds=i)).isoformat(),
        }
        for i in range(4)
    ]
    real = [
        {
            "agent_name": "heavi-chat",
            "event_type": "user_message",
            "content": f"real {i}",
            "session_id": f"conv-{i}",
            "created_at": (base + timedelta(minutes=1 + i)).isoformat(),
        }
        for i in range(2)
    ]
    await _push_events(client, key, curate_noise + real)

    feed = await curation_service.changes_since(uid, uid, old)
    assert [h["content"] for h in feed["history"]] == ["real 0", "real 1"]
    assert feed["history_has_more"] is False
    assert await curation_service.complete_through(
        uid, old, base + timedelta(hours=1)
    ) == base + timedelta(hours=1)


@pytest.mark.asyncio
async def test_feed_events_carry_session_folder(client: AsyncClient, _db_pool):
    """Folder placement is the owner's curation signal — 'mark this trace as
    sanctioned' is a move into a designated folder, so the feed must show each
    event's folder for the curator to honor the mark."""
    key, uid = await _register(client)
    old = datetime(2020, 1, 1, tzinfo=UTC)

    folder = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "Global — approved for learning", "external_key": "global"},
        headers=_auth(key),
    )
    await _push_events(
        client,
        key,
        [
            {
                "agent_name": "heavi-chat",
                "event_type": "user_message",
                "content": "sanctioned trace",
                "session_id": "conv-global",
                "session_folder_id": folder.json()["id"],
            }
        ],
    )

    feed = await curation_service.changes_since(uid, uid, old)
    marked = next(h for h in feed["history"] if h["content"] == "sanctioned trace")
    assert marked["folder"] == "Global — approved for learning"


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


def test_curator_prompt_demands_a_curator_log():
    """The run's final message is the home page's log entry — the prompt must
    demand it in log form, with the quiet-night escape hatch so empty deltas
    never get padded into fake activity."""
    prompt = prompts.render_curator_prompt("folder-123", "2026-08-01T00:00:00")
    assert "Curator log" in prompt
    assert "A quiet night is reported as quiet" in prompt


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
        "SELECT last_run_at, curated_through, last_run_outcome FROM agents WHERE id = $1",
        UUID(curator["id"]),
    )
    assert sprite_exec.calls == []  # no sprite wake
    assert row["curated_through"] == future  # watermark preserved
    # Tick consumed — the next beat won't re-check until the next cron tick.
    assert row["last_run_at"] > datetime.now(UTC) - timedelta(minutes=1)
    assert row["last_run_outcome"] == "skipped_no_changes"


@pytest.mark.asyncio
async def test_curator_run_does_not_echo_loop(
    client: AsyncClient, sprite_exec, _db_pool, monkeypatch
):
    """A curator run writes its own transcript into history_events; that must
    not count as new changes, or the daily gate would fire forever."""
    from backend.services import curation_service
    from backend.tasks.agent_schedules import _run_due, _run_scheduled_agent, run_scheduled_agent

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )
    await _make_due(_db_pool, curator["id"], datetime.now(UTC) - timedelta(minutes=2))

    dispatched = []
    monkeypatch.setattr(run_scheduled_agent, "delay", lambda *args: dispatched.append(args))
    assert await _run_due() == 1
    await _run_scheduled_agent(UUID(dispatched[0][0]), dispatched[0][1])

    row = await _db_pool.fetchrow(
        "SELECT curated_through, last_run_outcome FROM agents WHERE id = $1", UUID(curator["id"])
    )
    # Watermark advanced past the page change, and the run's own transcript
    # doesn't re-trigger the gate or appear in the feed.
    assert row["last_run_outcome"] == "ran"
    assert await curation_service.has_changes_since(uid, uid, row["curated_through"]) is False
    feed = await curation_service.changes_since(uid, uid, row["curated_through"])
    assert all(not str(e["session_id"] or "").startswith("agent-curate-") for e in feed["history"])


@pytest.mark.asyncio
async def test_curator_run_keeps_full_toolset(
    client: AsyncClient, sprite_exec, _db_pool, monkeypatch
):
    """The curator is a trusted headless run — it must NOT inherit the
    untrusted-channel tool restrictions (it needs to write the wiki)."""
    from backend.tasks.agent_schedules import _run_due, _run_scheduled_agent, run_scheduled_agent

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )
    await _make_due(_db_pool, curator["id"], datetime.now(UTC) - timedelta(minutes=2))

    dispatched = []
    monkeypatch.setattr(run_scheduled_agent, "delay", lambda *args: dispatched.append(args))
    await _run_due()
    await _run_scheduled_agent(UUID(dispatched[0][0]), dispatched[0][1])

    curator_argv = [a for a in sprite_exec.calls if "Memory Wiki Curation" in " ".join(a)]
    assert curator_argv and "--disallowedTools" not in curator_argv[0]


@pytest.mark.asyncio
async def test_failed_curator_run_preserves_watermark(
    client: AsyncClient, sprite_exec, _db_pool, monkeypatch
):
    """A failed run consumes the cron tick but must not advance the watermark —
    the un-curated delta is re-covered on the next successful run."""
    from backend.services import sprite_agent_service
    from backend.tasks.agent_schedules import _run_due, _run_scheduled_agent, run_scheduled_agent

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
    dispatched = []
    monkeypatch.setattr(run_scheduled_agent, "delay", lambda *args: dispatched.append(args))
    assert await _run_due() == 1
    await _run_scheduled_agent(UUID(dispatched[0][0]), dispatched[0][1])

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
    from backend.tasks.agent_schedules import _run_due, _run_scheduled_agent, run_scheduled_agent

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
    dispatched = []
    monkeypatch.setattr(run_scheduled_agent, "delay", lambda *args: dispatched.append(args))
    await _run_due()
    await _run_scheduled_agent(UUID(dispatched[0][0]), dispatched[0][1])

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
    assert await _run_due() == 1
    await _run_scheduled_agent(UUID(dispatched[1][0]), dispatched[1][1])
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

    # On-demand runs are independent of the nightly switch: a user who turned
    # the schedule off (curating locally) can still trigger a cloud pass.
    curator = await agent_service.get_or_create_curator(uid)
    await client.patch(
        f"/api/v1/me/agents/{curator['id']}", json={"run_mode": "chat"}, headers=_auth(key)
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
        "SELECT curated_through, last_run_at, last_run_outcome FROM agents WHERE id = $1",
        UUID(curator["id"]),
    )
    assert sprite_exec.calls  # the run actually woke the sprite
    assert row["curated_through"] >= before - timedelta(seconds=5)
    assert row["last_run_outcome"] == "ran"

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
async def test_manual_recompute_bookkeeping_failure_records_failed_outcome(
    client: AsyncClient, sprite_exec, _db_pool, monkeypatch
):
    """A successful turn is not a successful curator run until its watermark
    advances. The outcome must cover that post-turn work too."""
    from backend.services import curation_service
    from backend.tasks.agent_schedules import _run_curator_now

    _key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)

    async def boom(user_id, curated_through, now):
        raise RuntimeError("watermark write failed")

    monkeypatch.setattr(curation_service, "complete_through", boom)
    with pytest.raises(RuntimeError):
        await _run_curator_now(UUID(curator["id"]))

    row = await _db_pool.fetchrow(
        "SELECT last_run_error, last_run_outcome FROM agents WHERE id = $1",
        UUID(curator["id"]),
    )
    assert "watermark write failed" in row["last_run_error"]
    assert row["last_run_outcome"] == "failed"


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


@pytest.mark.asyncio
async def test_corrections_survive_a_delta_flooded_with_tool_traffic(
    client: AsyncClient, _db_pool, monkeypatch
):
    """The reason this input exists. Measured on a real account: 500 feed
    events held 295 tool events and 6 user messages, because tool traffic
    outnumbers user messages ~50:1 and the feed drains oldest-first. Skills
    are mined from the user's words, so those words cannot be left to compete
    for delta slots they will always lose."""
    monkeypatch.setattr(curation_service, "_MAX_EVENTS", 3)
    key, uid = await _register(client)
    now = datetime.now(UTC)

    await _push_events(
        client,
        key,
        [
            {
                "agent_name": "claude",
                "event_type": "tool_use",
                "content": f"ran a command {i}",
                "session_id": "s-noise",
                "created_at": (now - timedelta(days=3, minutes=i)).isoformat(),
            }
            for i in range(10)
        ]
        + [
            {
                "agent_name": "claude",
                "event_type": "user_message",
                "content": "no, never pkill by pattern",
                "session_id": "s-real",
                "created_at": (now - timedelta(days=1)).isoformat(),
            }
        ],
    )

    feed = await curation_service.changes_since(uid, uid, now - timedelta(days=10))
    assert feed["history_has_more"] is True
    assert all(h["event_type"] == "tool_use" for h in feed["history"])
    assert [c["content"] for c in feed["corrections"]] == ["no, never pkill by pattern"]
    assert feed["counts"]["corrections"] == 1


@pytest.mark.asyncio
async def test_corrections_ignore_the_watermark_so_recurrence_is_visible(
    client: AsyncClient, _db_pool
):
    """A skill earns its slot on recurrence across sessions, which one night's
    delta can never show. The window re-presents the same messages every run
    on purpose — if it respected the watermark, every message would be seen
    exactly once and no candidate could ever reach three sessions."""
    key, uid = await _register(client)
    now = datetime.now(UTC)
    await _push_events(
        client,
        key,
        [
            {
                "agent_name": "claude",
                "event_type": "user_message",
                "content": f"correction in session {i}",
                "session_id": f"s-{i}",
                "created_at": (now - timedelta(days=i + 1)).isoformat(),
            }
            for i in range(3)
        ],
    )

    # A watermark past every one of those events: the delta is empty, and the
    # corrections window still shows all three.
    feed = await curation_service.changes_since(uid, uid, now)
    assert feed["history"] == []
    assert len(feed["corrections"]) == 3
    assert len({c["session_id"] for c in feed["corrections"]}) == 3


@pytest.mark.asyncio
async def test_corrections_exclude_stale_messages_and_the_curators_own(
    client: AsyncClient, _db_pool
):
    """The window is recent-and-real: material older than the window is not
    evidence about how the user works now, and the curator's own transcripts
    would let it learn from behavior it caused."""
    key, uid = await _register(client)
    now = datetime.now(UTC)
    await _push_events(
        client,
        key,
        [
            {
                "agent_name": "claude",
                "event_type": "user_message",
                "content": "ancient history",
                "session_id": "s-old",
                "created_at": (now - timedelta(days=400)).isoformat(),
            },
            {
                "agent_name": "Memory curator",
                "event_type": "user_message",
                "content": "the curator talking to itself",
                "session_id": "agent-curate-123",
                "created_at": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "agent_name": "claude",
                "event_type": "user_message",
                "content": "this one counts",
                "session_id": "s-live",
                "created_at": (now - timedelta(hours=1)).isoformat(),
            },
        ],
    )

    feed = await curation_service.changes_since(uid, uid, now - timedelta(days=500))
    assert [c["content"] for c in feed["corrections"]] == ["this one counts"]


@pytest.mark.asyncio
async def test_one_chatty_session_cannot_crowd_out_the_others(
    client: AsyncClient, _db_pool, monkeypatch
):
    """Recurrence is counted in distinct sessions, so the sample maximizes
    sessions rather than messages. Newest-first-overall would have handed a
    single talkative session the whole window — measured on a real account,
    the newest 200 messages covered just 33 sessions over 1.4 days."""
    monkeypatch.setattr(curation_service, "_MAX_PER_SESSION", 2)
    key, uid = await _register(client)
    now = datetime.now(UTC)

    chatty = [
        {
            "agent_name": "claude",
            "event_type": "user_message",
            "content": f"chatty {i}",
            "session_id": "s-chatty",
            "created_at": (now - timedelta(minutes=i)).isoformat(),
        }
        for i in range(20)
    ]
    others = [
        {
            "agent_name": "claude",
            "event_type": "user_message",
            "content": f"quiet session {i}",
            "session_id": f"s-quiet-{i}",
            "created_at": (now - timedelta(days=i + 1)).isoformat(),
        }
        for i in range(3)
    ]
    await _push_events(client, key, chatty + others)

    corrections = await curation_service.recent_user_messages(uid, now)

    per_session: dict[str, int] = {}
    for c in corrections:
        per_session[c["session_id"]] = per_session.get(c["session_id"], 0) + 1
    assert per_session["s-chatty"] == 2
    assert {f"s-quiet-{i}" for i in range(3)} <= set(per_session)
    # Newest session first, so the curator reads current context before older.
    assert corrections[0]["session_id"] == "s-chatty"
