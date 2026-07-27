"""Mini programs and row enrichment.

Enrichment fills LLM-derived columns (Summary, Topics) on a mini program's
table. The properties that matter and are easy to regress:

  - the manifest is the single schema source, resolved to column ids;
  - a table is created once per (owner, slug) even under concurrency;
  - a row that can't be enriched records why and stops being retried, so one
    bad row can't wedge every later sweep;
  - unchanged rows are never re-sent to the model (that's the whole cost
    story on a bulk import);
  - topic labels converge on the existing vocabulary instead of drifting
    into synonyms, because that is what makes filtering by topic usable.
"""

import asyncio
from uuid import UUID

from httpx import AsyncClient

from backend.services import mini_program_query, mini_program_service, table_service
from backend.tasks import enrichment

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[dict, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, UUID(body["id"])


def _fake_model(payload: dict, calls: list[str] | None = None):
    """Stand in for llm.complete_json, recording the prompts it was sent."""

    async def _complete_json(*, prompt: str, system: str, tier=None, max_tokens=None):
        if calls is not None:
            calls.append(prompt)
        return payload

    return _complete_json


# --- Manifest ----------------------------------------------------------------


def test_manifest_resolves_column_names_to_ids():
    """The manifest names columns; the client needs ids. Anything the table
    doesn't have is dropped rather than emitted as a dangling name."""
    manifest = mini_program_service.BOOKMARKS_MANIFEST
    columns = [
        {"id": "col_title", "name": "Title", "type": "text"},
        {"id": "col_topics", "name": "Topics", "type": "multiselect"},
    ]
    resolved = mini_program_service.resolve(manifest, columns)

    assert resolved["detail"]["title"] == "col_title"
    assert resolved["detail"]["labels"] == "col_topics"
    # Summary/Site/URL aren't on this table, so no slot points at them.
    assert "body" not in resolved["detail"]
    assert resolved["enriched_columns"] == ["col_topics"]


async def test_ensure_table_is_idempotent_under_concurrency(client: AsyncClient, pool):
    """Bulk imports save many bookmarks at once across processes. Two
    concurrent ensure_table calls must yield one table, not two."""
    _, owner_id = await _register(client)

    tables = await asyncio.gather(
        *[
            mini_program_service.ensure_table(
                mini_program_service.BOOKMARKS_SLUG, owner_id, owner_id
            )
            for _ in range(4)
        ]
    )

    assert len({t["id"] for t in tables}) == 1
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM tables WHERE owner_user_id = $1 AND mini_program = 'bookmarks'",
        owner_id,
    )
    assert count == 1


async def test_new_table_is_seeded_with_views_and_enrichment(client: AsyncClient, pool):
    """A freshly created mini program table arrives usable: card views to
    render and an enrichment config for the worker to act on."""
    _, owner_id = await _register(client)
    table = await mini_program_service.ensure_table(
        mini_program_service.BOOKMARKS_SLUG, owner_id, owner_id
    )

    row = await pool.fetchrow(
        "SELECT views, enrichment_config, mini_program FROM tables WHERE id = $1", table["id"]
    )
    assert row["mini_program"] == "bookmarks"
    assert [v["layout"] for v in row["views"]] == ["cards", "cards", "table"]
    assert row["enrichment_config"]["enabled"] is True
    assert len(row["enrichment_config"]["targets"]) == 2


# --- The worker --------------------------------------------------------------


async def _bookmarks_row(client: AsyncClient, owner_id: UUID, pool, **cells):
    """Create a Bookmarks row with cells addressed by column name."""
    table = await mini_program_service.ensure_table(
        mini_program_service.BOOKMARKS_SLUG, owner_id, owner_id
    )
    ids = {c["name"]: c["id"] for c in table["columns"]}
    row = await table_service.create_row(
        table["id"], {ids[name]: value for name, value in cells.items()}, owner_id
    )
    return table, ids, row


async def test_enrichment_fills_summary_and_topics(client: AsyncClient, pool, monkeypatch):
    """The payoff: a saved bookmark gains a summary and topic labels without
    the user doing anything."""
    _, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(
        client, owner_id, pool, Title="Why Simplicity Wins", Site="example.com"
    )

    monkeypatch.setattr(
        enrichment.llm,
        "complete_json",
        _fake_model({"summary": "A case for simple code.", "topics": ["Engineering"]}),
    )
    assert await enrichment._reconcile() == 1

    stored = await pool.fetchrow(
        "SELECT data, enrich_stale, enrich_error FROM table_rows WHERE id = $1", row["id"]
    )
    assert stored["data"][ids["Summary"]] == "A case for simple code."
    assert stored["data"][ids["Topics"]] == ["Engineering"]
    assert stored["enrich_stale"] is False
    assert stored["enrich_error"] is None


async def test_unchanged_row_is_not_sent_to_the_model_again(client: AsyncClient, pool, monkeypatch):
    """Re-importing a library must not re-pay for rows already enriched. The
    content hash — not the stale flag alone — is what guarantees that."""
    _, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(client, owner_id, pool, Title="Stable Title")

    calls: list[str] = []
    monkeypatch.setattr(
        enrichment.llm,
        "complete_json",
        _fake_model({"summary": "First pass.", "topics": ["Engineering"]}, calls),
    )
    await enrichment._reconcile()
    assert len(calls) == 1

    # Re-queue the row without changing its content.
    await pool.execute("UPDATE table_rows SET enrich_stale = TRUE WHERE id = $1", row["id"])
    await enrichment._reconcile()
    assert len(calls) == 1, "unchanged content must not trigger a second model call"


async def test_failed_row_records_the_error_and_stops_retrying(
    client: AsyncClient, pool, monkeypatch
):
    """A row the model chokes on must not be re-selected forever — every
    later sweep would stall behind it. The reason is recorded, not swallowed."""
    _, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(client, owner_id, pool, Title="Poison Row")

    async def _boom(**_kwargs):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(enrichment.llm, "complete_json", _boom)
    await enrichment._reconcile()

    stored = await pool.fetchrow(
        "SELECT enrich_stale, enrich_error FROM table_rows WHERE id = $1", row["id"]
    )
    assert stored["enrich_stale"] is False
    assert "model exploded" in stored["enrich_error"]


async def test_link_only_bookmark_is_settled_not_retried(client: AsyncClient, pool, monkeypatch):
    """A bookmark with no title and no captured page has nothing to enrich.
    It settles with a reason rather than looping."""
    _, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(client, owner_id, pool, Type="Link")

    calls: list[str] = []
    monkeypatch.setattr(enrichment.llm, "complete_json", _fake_model({}, calls))
    await enrichment._reconcile()

    stored = await pool.fetchrow(
        "SELECT enrich_stale, enrich_error FROM table_rows WHERE id = $1", row["id"]
    )
    assert stored["enrich_stale"] is False
    assert stored["enrich_error"] == "no source text to enrich from"
    assert calls == [], "nothing to summarise means no model call"


# --- Topic vocabulary --------------------------------------------------------


async def test_new_labels_join_the_column_vocabulary(client: AsyncClient, pool, monkeypatch):
    """Topics is a multiselect: its options are the filter chips the user
    clicks. A label the model invents has to land there or it can't be
    filtered on."""
    _, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(client, owner_id, pool, Title="Agent Memory Design")

    monkeypatch.setattr(
        enrichment.llm,
        "complete_json",
        _fake_model({"summary": "On agent memory.", "topics": ["Agent Memory"]}),
    )
    await enrichment._reconcile()

    columns = await pool.fetchval("SELECT columns FROM tables WHERE id = $1", table["id"])
    topics = next(c for c in columns if c["id"] == ids["Topics"])
    assert "Agent Memory" in (topics["options"] or [])


async def test_existing_vocabulary_is_offered_to_the_model(client: AsyncClient, pool, monkeypatch):
    """Independent per-row labelling drifts into synonyms ("AI agents",
    "agentic AI", "LLM agents"), which makes topic filtering useless. The
    established vocabulary is fed back in so the model reuses it."""
    _, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(client, owner_id, pool, Title="Another Agent Post")

    # Seed an established vocabulary on the Topics column.
    columns = await pool.fetchval("SELECT columns FROM tables WHERE id = $1", table["id"])
    for column in columns:
        if column["id"] == ids["Topics"]:
            column["options"] = ["Agent Memory", "Engineering"]
    await pool.execute("UPDATE tables SET columns = $1 WHERE id = $2", columns, table["id"])

    calls: list[str] = []
    monkeypatch.setattr(
        enrichment.llm,
        "complete_json",
        _fake_model({"summary": "More on agents.", "topics": ["Agent Memory"]}, calls),
    )
    await enrichment._reconcile()

    assert "Agent Memory" in calls[0]
    assert "Engineering" in calls[0]

    # And reusing an existing label must not duplicate it in the options.
    columns = await pool.fetchval("SELECT columns FROM tables WHERE id = $1", table["id"])
    topics = next(c for c in columns if c["id"] == ids["Topics"])
    assert topics["options"].count("Agent Memory") == 1


async def test_vocabulary_is_bootstrapped_before_the_first_row_is_labelled(
    client: AsyncClient, pool, monkeypatch
):
    """Labelling row-by-row from an empty vocabulary has nothing to converge
    on, so every row invents its own labels — five saves produced eighteen
    near-synonyms before this existed. One pass over the titles seeds a
    vocabulary that later rows reuse."""
    _, owner_id = await _register(client)
    table = await mini_program_service.ensure_table(
        mini_program_service.BOOKMARKS_SLUG, owner_id, owner_id
    )
    ids = {c["name"]: c["id"] for c in table["columns"]}
    for i in range(enrichment.BOOTSTRAP_MIN_ROWS):
        await table_service.create_row(table["id"], {ids["Title"]: f"Article {i}"}, owner_id)

    prompts: list[str] = []

    async def _complete_json(*, prompt: str, system: str, tier=None, max_tokens=None):
        prompts.append(prompt)
        if "Propose up to" in prompt:
            return {"topics": ["Databases", "AI Engineering"]}
        return {"summary": "A summary.", "topics": ["Databases"]}

    monkeypatch.setattr(enrichment.llm, "complete_json", _complete_json)
    await enrichment._reconcile()

    assert any("Propose up to" in p for p in prompts), "expected a bootstrap pass"
    # The bootstrapped vocabulary must reach the row prompts, or it bought nothing.
    row_prompts = [p for p in prompts if "Propose up to" not in p]
    assert "Databases" in row_prompts[0]


async def test_bootstrap_is_skipped_once_a_vocabulary_exists(
    client: AsyncClient, pool, monkeypatch
):
    """Bootstrap is a one-off. Re-running it every sweep would burn a
    quality-tier call per batch forever."""
    _, owner_id = await _register(client)
    table = await mini_program_service.ensure_table(
        mini_program_service.BOOKMARKS_SLUG, owner_id, owner_id
    )
    ids = {c["name"]: c["id"] for c in table["columns"]}
    columns = await pool.fetchval("SELECT columns FROM tables WHERE id = $1", table["id"])
    for column in columns:
        if column["id"] == ids["Topics"]:
            column["options"] = ["Databases"]
    await pool.execute("UPDATE tables SET columns = $1 WHERE id = $2", columns, table["id"])
    for i in range(enrichment.BOOTSTRAP_MIN_ROWS):
        await table_service.create_row(table["id"], {ids["Title"]: f"Article {i}"}, owner_id)

    prompts: list[str] = []
    monkeypatch.setattr(
        enrichment.llm,
        "complete_json",
        _fake_model({"summary": "A summary.", "topics": ["Databases"]}, prompts),
    )
    await enrichment._reconcile()

    assert not any("Propose up to" in p for p in prompts)


async def test_labels_from_one_batch_reach_the_next(client: AsyncClient, pool, monkeypatch):
    """Convergence accrues across batches, not within one.

    Rows in a batch run concurrently — serially, a batch outlasted the beat
    interval, which is what made a large import an overnight job. The cost is
    that rows in the *same* batch can't see each other's labels; bootstrap
    covers that by seeding a vocabulary before the first batch. What must
    hold is that a label written by one batch is offered to the next.
    """
    _, owner_id = await _register(client)
    table = await mini_program_service.ensure_table(
        mini_program_service.BOOKMARKS_SLUG, owner_id, owner_id
    )
    ids = {c["name"]: c["id"] for c in table["columns"]}
    await table_service.create_row(table["id"], {ids["Title"]: "First Article"}, owner_id)

    prompts: list[str] = []

    async def _complete_json(*, prompt: str, system: str, tier=None, max_tokens=None):
        if "Propose up to" in prompt:
            return {"topics": []}  # bootstrap declines, so only rows build the vocabulary
        prompts.append(prompt)
        return {"summary": "A summary.", "topics": ["Invented Topic"]}

    monkeypatch.setattr(enrichment.llm, "complete_json", _complete_json)
    await enrichment._reconcile()
    assert "Invented Topic" not in prompts[0], "first row starts with no vocabulary"

    # A later save, enriched by a later sweep, must be offered that label.
    await table_service.create_row(table["id"], {ids["Title"]: "Second Article"}, owner_id)
    await enrichment._reconcile()

    assert len(prompts) == 2
    assert "Invented Topic" in prompts[1], "the next batch must see the earlier label"


async def test_a_claimed_row_is_not_handed_to_a_second_sweep(
    client: AsyncClient, pool, monkeypatch
):
    """Claiming clears the queue flag up front. A plain SELECT left rows
    flagged for the whole model call, and since a batch outlasts the beat
    interval, overlapping sweeps re-selected the same rows and paid twice."""
    _, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(client, owner_id, pool, Title="Contended Row")

    calls: list[str] = []

    async def _slow(*, prompt: str, system: str, tier=None, max_tokens=None):
        calls.append(prompt)
        await asyncio.sleep(0.2)  # still in flight when the second sweep starts
        return {"summary": "A summary.", "topics": ["Engineering"]}

    monkeypatch.setattr(enrichment.llm, "complete_json", _slow)
    await asyncio.gather(enrichment._reconcile(), enrichment._reconcile())

    row_calls = [c for c in calls if "Propose up to" not in c]
    assert len(row_calls) == 1, "overlapping sweeps must not both enrich the row"


# --- API ---------------------------------------------------------------------


async def test_app_endpoint_resolves_slug_to_the_users_table(client: AsyncClient):
    """/apps/<slug> is what makes the app URL stable and shareable — it has
    to resolve to *this* user's table, and 404 before they have one."""
    headers, owner_id = await _register(client)

    missing = await client.get("/api/v1/me/apps/bookmarks", headers=headers)
    assert missing.status_code == 404

    installed = await client.post("/api/v1/me/apps/bookmarks", headers=headers)
    assert installed.status_code == 201
    table_id = installed.json()["table_id"]

    resolved = await client.get("/api/v1/me/apps/bookmarks", headers=headers)
    assert resolved.status_code == 200
    assert resolved.json()["table_id"] == table_id
    assert resolved.json()["manifest"]["detail"]["title"]


async def test_install_is_idempotent(client: AsyncClient):
    """Installing twice must not fork the user's library into two tables."""
    headers, _ = await _register(client)
    first = await client.post("/api/v1/me/apps/bookmarks", headers=headers)
    second = await client.post("/api/v1/me/apps/bookmarks", headers=headers)
    assert first.json()["table_id"] == second.json()["table_id"]


async def test_app_gallery_flags_what_is_installed(client: AsyncClient):
    """The gallery distinguishes apps the user has from ones they could add."""
    headers, _ = await _register(client)

    before = await client.get("/api/v1/me/apps", headers=headers)
    assert before.json()["apps"][0]["installed"] is False

    await client.post("/api/v1/me/apps/bookmarks", headers=headers)
    after = await client.get("/api/v1/me/apps", headers=headers)
    assert after.json()["apps"][0]["installed"] is True


async def test_reenrich_requeues_a_row(client: AsyncClient, pool):
    """The detail pane's "regenerate" has to clear the hash too, or the sweep
    skips the row as unchanged and nothing happens."""
    headers, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(client, owner_id, pool, Title="Some Article")
    await pool.execute(
        "UPDATE table_rows SET enrich_stale = FALSE, enrich_hash = 'abc' WHERE id = $1", row["id"]
    )

    resp = await client.post(
        f"/api/v1/me/apps/bookmarks/rows/{row['id']}/reenrich", headers=headers
    )
    assert resp.status_code == 200

    stored = await pool.fetchrow(
        "SELECT enrich_stale, enrich_hash FROM table_rows WHERE id = $1", row["id"]
    )
    assert stored["enrich_stale"] is True
    assert stored["enrich_hash"] is None


async def test_reenrich_cannot_touch_another_users_row(client: AsyncClient, pool):
    """Row ids are guessable UUIDs; the endpoint must scope by the caller's
    own table, not just look the row up by id."""
    _, victim_id = await _register(client)
    _, victim_row = (await _bookmarks_row(client, victim_id, pool, Title="Private"))[1:]

    attacker_headers, attacker_id = await _register(client)
    await mini_program_service.ensure_table(
        mini_program_service.BOOKMARKS_SLUG, attacker_id, attacker_id
    )

    resp = await client.post(
        f"/api/v1/me/apps/bookmarks/rows/{victim_row['id']}/reenrich", headers=attacker_headers
    )
    assert resp.status_code == 404


async def test_saved_views_survive_the_table_response(client: AsyncClient):
    """The app shell picks its layout from the table's saved views. They are
    stored as free-form dicts, so a response model that omits the field drops
    them silently and every app falls back to the default layout."""
    headers, _ = await _register(client)
    installed = await client.post("/api/v1/me/apps/bookmarks", headers=headers)
    table_id = installed.json()["table_id"]

    resp = await client.get(f"/api/v1/tables/{table_id}", headers=headers)
    assert resp.status_code == 200
    views = resp.json()["views"]
    assert [v["name"] for v in views] == ["Recent", "By topic", "All rows"]
    assert [v["layout"] for v in views] == ["cards", "cards", "table"]


# --- Filters, paging, editing -------------------------------------------------


def test_url_normalization_collapses_cosmetic_differences():
    """Duplicate detection is only useful if the same article saved from two
    places collapses to one key — and only safe if genuinely different pages
    never do."""
    n = mini_program_query.normalize_url
    base = n("https://example.com/post")
    assert n("http://www.example.com/post/") == base
    assert n("https://example.com/post?utm_source=twitter&fbclid=abc") == base
    # A meaningful query param is not cosmetic.
    assert n("https://example.com/post?page=2") != base
    # Nor is a different path.
    assert n("https://example.com/other") != base


async def test_duplicates_filter_keeps_the_original(client: AsyncClient, pool):
    """'Delete duplicates' must leave one copy behind, so the first save of a
    URL is never itself reported as a duplicate."""
    headers, owner_id = await _register(client)
    table, ids, _ = await _bookmarks_row(
        client, owner_id, pool, Title="Original", URL="https://example.com/a"
    )
    await table_service.create_row(
        table["id"], {ids["Title"]: "Repeat", ids["URL"]: "https://www.example.com/a/"}, owner_id
    )
    await table_service.create_row(
        table["id"], {ids["Title"]: "Different", ids["URL"]: "https://example.com/b"}, owner_id
    )

    resp = await client.get("/api/v1/me/apps/bookmarks/rows?filter=duplicates", headers=headers)
    titles = [r["data"][ids["Title"]] for r in resp.json()["rows"]]
    assert titles == ["Repeat"]

    facets = (await client.get("/api/v1/me/apps/bookmarks/facets", headers=headers)).json()
    assert facets["duplicates"] == 1
    assert facets["total"] == 3


async def test_search_and_filters_span_the_whole_table_not_a_page(client: AsyncClient, pool):
    """The client used to filter over its loaded page, so a large library
    searched only its first 100 items. Paging must not shrink the corpus."""
    headers, owner_id = await _register(client)
    table, ids, _ = await _bookmarks_row(client, owner_id, pool, Title="Needle Article")
    for i in range(70):
        await table_service.create_row(table["id"], {ids["Title"]: f"Filler {i}"}, owner_id)

    first = await client.get("/api/v1/me/apps/bookmarks/rows?limit=10", headers=headers)
    assert first.json()["total"] == 71
    assert len(first.json()["rows"]) == 10
    assert first.json()["has_more"] is True

    # The needle is the oldest row, far outside the first page.
    hit = await client.get("/api/v1/me/apps/bookmarks/rows?q=needle&limit=10", headers=headers)
    assert hit.json()["total"] == 1


async def test_paging_walks_the_whole_library(client: AsyncClient, pool):
    headers, owner_id = await _register(client)
    table, ids, _ = await _bookmarks_row(client, owner_id, pool, Title="Row 0")
    for i in range(1, 25):
        await table_service.create_row(table["id"], {ids["Title"]: f"Row {i}"}, owner_id)

    seen = []
    for offset in (0, 10, 20):
        page = await client.get(
            f"/api/v1/me/apps/bookmarks/rows?limit=10&offset={offset}", headers=headers
        )
        seen.extend(r["id"] for r in page.json()["rows"])
    assert len(seen) == 25
    assert len(set(seen)) == 25, "pages must not overlap or repeat rows"


async def test_untagged_filter_and_manual_topic_edit(client: AsyncClient, pool):
    """A manual topic edit has to move the row out of Untagged and add the
    label to the column vocabulary, or it can't be filtered on afterwards."""
    headers, owner_id = await _register(client)
    table, ids, row = await _bookmarks_row(client, owner_id, pool, Title="No Topics Yet")

    before = (await client.get("/api/v1/me/apps/bookmarks/facets", headers=headers)).json()
    assert before["untagged"] == 1

    resp = await client.put(
        f"/api/v1/me/apps/bookmarks/rows/{row['id']}/topics",
        json={"topics": ["Hand Picked"]},
        headers=headers,
    )
    assert resp.status_code == 200

    after = (await client.get("/api/v1/me/apps/bookmarks/facets", headers=headers)).json()
    assert after["untagged"] == 0
    assert {"label": "Hand Picked", "count": 1} in after["topics"]

    columns = await pool.fetchval("SELECT columns FROM tables WHERE id = $1", table["id"])
    topics_col = next(c for c in columns if c["id"] == ids["Topics"])
    assert "Hand Picked" in topics_col["options"]


async def test_bulk_add_topics_unions_rather_than_replaces(client: AsyncClient, pool):
    """Bulk tagging must not silently discard labels the rows already have."""
    headers, owner_id = await _register(client)
    table, ids, first = await _bookmarks_row(client, owner_id, pool, Title="Has A Topic")
    await client.put(
        f"/api/v1/me/apps/bookmarks/rows/{first['id']}/topics",
        json={"topics": ["Existing"]},
        headers=headers,
    )
    second = await table_service.create_row(table["id"], {ids["Title"]: "Bare"}, owner_id)

    resp = await client.post(
        "/api/v1/me/apps/bookmarks/rows/bulk",
        json={
            "row_ids": [str(first["id"]), str(second["id"])],
            "action": "add_topics",
            "topics": ["Added"],
        },
        headers=headers,
    )
    assert resp.json()["affected"] == 2

    stored = await pool.fetch(
        "SELECT data FROM table_rows WHERE table_id = $1 ORDER BY row_order", table["id"]
    )
    assert stored[0]["data"][ids["Topics"]] == ["Existing", "Added"]
    assert stored[1]["data"][ids["Topics"]] == ["Added"]


async def test_bulk_delete_removes_only_the_selection(client: AsyncClient, pool):
    headers, owner_id = await _register(client)
    table, ids, keep = await _bookmarks_row(client, owner_id, pool, Title="Keep")
    doomed = await table_service.create_row(table["id"], {ids["Title"]: "Delete"}, owner_id)

    resp = await client.post(
        "/api/v1/me/apps/bookmarks/rows/bulk",
        json={"row_ids": [str(doomed["id"])], "action": "delete"},
        headers=headers,
    )
    assert resp.json()["affected"] == 1
    remaining = await pool.fetch("SELECT data FROM table_rows WHERE table_id = $1", table["id"])
    assert [r["data"][ids["Title"]] for r in remaining] == ["Keep"]


async def test_bulk_edit_cannot_reach_another_users_rows(client: AsyncClient, pool):
    """Row ids are supplied by the client, so the table is resolved from the
    caller's own slug and every id is scoped to it."""
    _, victim_id = await _register(client)
    _, _, victim_row = await _bookmarks_row(client, victim_id, pool, Title="Private")

    attacker_headers, attacker_id = await _register(client)
    await mini_program_service.ensure_table(
        mini_program_service.BOOKMARKS_SLUG, attacker_id, attacker_id
    )

    resp = await client.post(
        "/api/v1/me/apps/bookmarks/rows/bulk",
        json={"row_ids": [str(victim_row["id"])], "action": "delete"},
        headers=attacker_headers,
    )
    assert resp.json()["affected"] == 0
    survived = await pool.fetchval(
        "SELECT count(*) FROM table_rows WHERE id = $1", victim_row["id"]
    )
    assert survived == 1
