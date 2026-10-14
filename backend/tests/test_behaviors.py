# ruff: noqa: F811 -- pytest fixtures imported from test_model_wizard are used as parameters
"""Behaviors: rule and model detectors over trace windows, trends, alerts, search, datasets."""

from uuid import UUID

import pytest

from backend.services import embeddings, llm
from backend.services.behaviors import alerts, builtin, detect, scan, segments
from backend.tasks import embeddings as embedding_tasks

from .test_model_wizard import WordsEmbedder, _auth, fakes  # noqa: F401 -- fixtures

B = "/api/v1/behaviors"

STEPS = [
    ("user", "Find the refund policy for order 88", None),
    ("assistant", "", "search_kb"),
    ("tool", "[]", None),
    ("assistant", "Refunds are not possible for that order.", None),
    ("user", "That's wrong. Find the refund policy for order 88 again", None),
    ("assistant", "Refunds are allowed within 30 days.", None),
]

# Step labels as the labeler stores them: keyed by step index.
LABELS = {
    "0": {
        "actor": "user",
        "intent": "new_request",
        "sentiment": "neutral",
        "task_id": "t1",
        "evidence": "Find the refund policy",
    },
    "1": {
        "actor": "agent",
        "type": "tool_call",
        "result": "empty",
        "tool": "search_kb",
        "task_id": "t1",
        "evidence": "[]",
        "duplicate_of": None,
    },
    "3": {
        "actor": "agent",
        "type": "output",
        "is_output": True,
        "stance": "asserted",
        "outcome": "answer",
        "task_id": "t1",
        "evidence": "Refunds are not possible",
    },
    "4": {
        "actor": "user",
        "intent": "repeat_request",
        "sentiment": "negative",
        "task_id": "t1",
        "evidence": "That's wrong",
    },
    "5": {
        "actor": "agent",
        "type": "output",
        "is_output": True,
        "stance": "asserted",
        "outcome": "answer",
        "task_id": "t1",
        "evidence": "within 30 days",
    },
}


async def _me(pool, auth) -> UUID:
    from backend.auth import hash_api_key

    return await pool.fetchval(
        "SELECT user_id FROM user_api_keys WHERE key_hash = $1",
        hash_api_key(auth["Authorization"][7:]),
    )


async def _trace(pool, owner_id, steps=STEPS, labels=LABELS, title="Refund ticket") -> UUID:
    trace_id = await pool.fetchval(
        """INSERT INTO rm_traces(owner_user_id, external_id, title, source_format, created_at, updated_at)
           VALUES ($1, gen_random_uuid()::text, $2, 'stash', now() - interval '1 minute', now() - interval '1 minute')
           RETURNING id""",
        owner_id,
        title,
    )
    for idx, (role, content, tool) in enumerate(steps):
        await pool.execute(
            "INSERT INTO rm_trace_steps(trace_id, idx, role, content, tool_name) VALUES ($1, $2, $3, $4, $5)",
            trace_id, idx, role, content, tool,
        )  # fmt: skip
    if labels is not None:
        await pool.execute(
            """INSERT INTO rm_step_labels(trace_id, owner_user_id, fingerprint, labels, rewards, summary, chunks, label_model)
               VALUES ($1, $2, 'x', $3, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, 'test')""",
            trace_id,
            owner_id,
            labels,
        )
    return trace_id


def test_rules_tag_the_windows_they_describe():
    steps = [
        {"idx": i, "role": r, "content": c, "tool_name": t} for i, (r, c, t) in enumerate(STEPS)
    ]
    assert builtin.detect({"kind": "repeat_request"}, LABELS, steps) == [
        {
            "start_idx": 4,
            "end_idx": 4,
            "confidence": 1.0,
            "evidence": [{"idx": 4, "quote": "That's wrong"}],
            "note": "",
        }
    ]
    # An empty lookup followed straight by an answer is a premature stop over the whole window.
    stop = builtin.detect({"kind": "premature_stop"}, LABELS, steps)
    assert [(w["start_idx"], w["end_idx"]) for w in stop] == [(1, 3)]
    # Neither answer had a tool result behind it; touching windows merge into one.
    claims = builtin.detect({"kind": "unsupported_claim"}, LABELS, steps)
    assert [(w["start_idx"], w["end_idx"]) for w in claims] == [(0, 5)]
    backed = {**LABELS, "1": {**LABELS["1"], "result": "data"}}
    assert builtin.detect({"kind": "unsupported_claim"}, backed, steps) == []


def test_segments_cut_at_user_turns():
    steps = [
        {"idx": i, "role": r, "content": c, "tool_name": t, "tool_input": None}
        for i, (r, c, t) in enumerate(STEPS)
    ]
    built = segments.build(
        [{"idx": 99, "role": "system", "content": "sys", "tool_name": None}] + steps
    )
    assert [(s["start_idx"], s["end_idx"]) for s in built] == [(0, 3), (4, 5)]
    assert "[1] ASSISTANT tool call search_kb" in built[0]["text"]


async def test_starters_scan_trend_review_and_version_bump(client, pool):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    created = (await client.post(f"{B}/starters", headers=auth, json={})).json()["created"]
    assert {b["rule"]["kind"] for b in created} == set(builtin.RULES)
    # Installing again adds nothing.
    assert (await client.post(f"{B}/starters", headers=auth, json={})).json()["created"] == []
    trace_id = await _trace(pool, owner)
    for b in created:
        await scan.scan_trace(await scan.get_behavior(UUID(b["id"])), trace_id)
    hits = (await client.get(f"{B}/traces/{trace_id}/hits", headers=auth)).json()["hits"]
    names = {h["behavior_name"] for h in hits}
    assert {
        "Repeats the request",
        "Stops after an empty lookup",
        "Empty tool result",
        "User frustration",
    } <= names
    repeat = next(b for b in created if b["rule"]["kind"] == "repeat_request")

    overview = (await client.get(f"{B}/monitoring?days=7", headers=auth)).json()
    row = next(r for r in overview["behaviors"] if r["behavior"]["id"] == repeat["id"])
    assert row["last_7_days"] == 1 and row["series"][-1]["rate"] == 1.0

    hit = (await client.get(f"{B}/{repeat['id']}/hits", headers=auth)).json()["hits"][0]
    reviewed = await client.post(
        f"{B}/hits/{hit['id']}/review", headers=auth, json={"verdict": "confirmed"}
    )
    assert reviewed.status_code == 200 and reviewed.json()["review"] == "confirmed"
    stop = next(b for b in created if b["rule"]["kind"] == "premature_stop")
    # Changing what a behavior means drops its unreviewed hits; reviews survive.
    edited = await client.patch(
        f"{B}/{stop['id']}", headers=auth, json={"rule": {"kind": "tool_error"}}
    )
    assert edited.status_code == 200 and edited.json()["version"] == 2
    assert (await client.get(f"{B}/{stop['id']}/hits", headers=auth)).json()["hits"] == []
    renamed = await client.patch(f"{B}/{repeat['id']}", headers=auth, json={"name": "Asks again"})
    assert renamed.json()["version"] == 1
    assert len((await client.get(f"{B}/{repeat['id']}/hits", headers=auth)).json()["hits"]) == 1

    other = await _auth(client)
    assert (await client.get(f"{B}/{repeat['id']}", headers=other)).status_code == 404
    assert (
        await client.post(
            f"{B}/hits/{hit['id']}/review", headers=other, json={"verdict": "rejected"}
        )
    ).status_code == 404


async def test_rule_waits_for_labels_and_reconcile_picks_it_up(client, pool, monkeypatch):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    behavior = (
        await client.post(
            f"{B}",
            headers=auth,
            json={
                "name": "Asks again",
                "actor": "user",
                "detector": "rule",
                "rule": {"kind": "repeat_request"},
            },
        )
    ).json()
    trace_id = await _trace(pool, owner, labels=None)
    b = await scan.get_behavior(UUID(behavior["id"]))
    assert (await scan.scan_trace(b, trace_id))["state"] == scan.NO_LABELS
    await pool.execute(
        """INSERT INTO rm_step_labels(trace_id, owner_user_id, fingerprint, labels, rewards, summary, chunks, label_model, labeled_at)
           VALUES ($1, $2, 'x', $3, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, 'test', now() + interval '1 second')""",
        trace_id, owner, LABELS,
    )  # fmt: skip
    monkeypatch.setattr(scan, "SCAN_BATCH", 10_000)
    monkeypatch.setattr(alerts, "evaluate", _no_alerts)
    await scan.reconcile()
    assert (
        await pool.fetchval("SELECT count(*) FROM behavior_hits WHERE trace_id = $1", trace_id) == 1
    )
    # Reconcile also cut the trace into searchable segments.
    assert (
        await pool.fetchval("SELECT count(*) FROM rm_trace_segments WHERE trace_id = $1", trace_id)
        == 2
    )


async def _no_alerts() -> int:
    return 0


def _detector(calls: list):
    async def fake(*, prompt, system, output_model, tier, max_tokens):
        calls.append(prompt)
        if "refund" in prompt.lower() and "[0]" in prompt:
            return detect.Detection(
                hits=[
                    detect.Hit(start_idx=1, end_idx=3, confidence=0.8,
                               evidence=[detect.Evidence(idx=2, quote="[]"), detect.Evidence(idx=40, quote="outside")],
                               note="gave up")
                ]
            )  # fmt: skip
        return detect.Detection(
            hits=[detect.Hit(start_idx=50, end_idx=60, confidence=0.9, evidence=[])]
        )

    return fake


async def test_model_detector_reads_each_segment_once(client, pool, monkeypatch, fakes):
    calls: list[str] = []
    monkeypatch.setattr(llm, "complete_structured", _detector(calls))
    auth = await _auth(client)
    owner = await _me(pool, auth)
    resp = await client.post(
        f"{B}",
        headers=auth,
        json={
            "name": "Gives up on refunds",
            "actor": "agent",
            "definition": "The agent stops looking after an empty refund search.",
        },
    )
    assert resp.status_code == 201, resp.text
    b = await scan.get_behavior(UUID(resp.json()["id"]))
    trace_id = await _trace(pool, owner)
    first = await scan.scan_trace(b, trace_id)
    assert first == {"state": "done", "added": 1} and len(calls) == 2
    hit = await pool.fetchrow("SELECT * FROM behavior_hits WHERE trace_id = $1", trace_id)
    # Windows are clipped to the segment they came from; out-of-segment evidence is dropped.
    assert (hit["start_idx"], hit["end_idx"]) == (1, 3) and [e["idx"] for e in hit["evidence"]] == [
        2
    ]
    # The trace grows by one turn: only the new segment is read.
    await pool.execute(
        "INSERT INTO rm_trace_steps(trace_id, idx, role, content) VALUES ($1, 6, 'user', 'thanks'), ($1, 7, 'assistant', 'welcome')",
        trace_id,
    )
    await pool.execute("UPDATE rm_traces SET updated_at = now() WHERE id = $1", trace_id)
    previous = dict(
        await pool.fetchrow("SELECT * FROM behavior_scans WHERE trace_id = $1", trace_id)
    )
    again = await scan.scan_trace(b, trace_id, previous)
    assert again["state"] == "done" and len(calls) == 3
    assert (
        await pool.fetchval("SELECT count(*) FROM behavior_hits WHERE trace_id = $1", trace_id) == 1
    )
    # A model definition is required.
    bad = await client.post(f"{B}", headers=auth, json={"name": "x", "actor": "agent"})
    assert bad.status_code == 422


class SegmentEmbedder(WordsEmbedder):
    dims = 384  # the stored segment vectors are vector(384)


@pytest.fixture
def segment_embedder():
    previous = embeddings.get_embedder()
    embeddings.set_embedder(SegmentEmbedder())
    yield
    embeddings.set_embedder(previous)


async def test_search_finds_windows_and_filters_by_behavior(client, pool, segment_embedder):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    refund = await _trace(pool, owner)
    other = await _trace(
        pool, owner, steps=[("user", "Write a haiku about autumn", None), ("assistant", "Leaves fall", None)],
        labels={}, title="Poem",
    )  # fmt: skip
    for t in (refund, other):
        await segments.sync(t, owner)
    while await embedding_tasks._reconcile_trace_segments():
        pass
    resp = await client.get(f"{B}/search", headers=auth, params={"q": "refund policy order lookup"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "semantic"
    assert body["results"][0]["trace_id"] == str(refund)
    assert {s["start_idx"] for s in body["results"][0]["segments"]} == {0, 4}
    assert body["results"][0]["input"].startswith("Find the refund policy")

    behavior = (
        await client.post(
            f"{B}",
            headers=auth,
            json={
                "name": "Asks again",
                "actor": "user",
                "detector": "rule",
                "rule": {"kind": "repeat_request"},
            },
        )
    ).json()
    await scan.scan_trace(await scan.get_behavior(UUID(behavior["id"])), refund)
    filtered = (
        await client.get(f"{B}/search", headers=auth, params={"behaviors": behavior["id"]})
    ).json()
    assert [r["trace_id"] for r in filtered["results"]] == [str(refund)]
    assert filtered["results"][0]["behaviors"][0]["name"] == "Asks again"
    # Other owners never see these traces.
    stranger = await _auth(client)
    assert (await client.get(f"{B}/search", headers=stranger, params={"q": "refund"})).json()[
        "results"
    ] == []


async def test_alert_fires_once_per_cooldown(client, pool, monkeypatch):
    sent = []

    async def deliver(behavior, text):
        sent.append(text)
        return ["slack"]

    monkeypatch.setattr(alerts, "deliver", deliver)
    auth = await _auth(client)
    owner = await _me(pool, auth)
    behavior = (
        await client.post(
            f"{B}",
            headers=auth,
            json={"name": "Asks again", "actor": "user", "detector": "rule", "rule": {"kind": "repeat_request"},
                  "alert": {"threshold": 1, "window_hours": 24}},
        )
    ).json()  # fmt: skip
    await scan.scan_trace(await scan.get_behavior(UUID(behavior["id"])), await _trace(pool, owner))
    await alerts.evaluate()
    await alerts.evaluate()
    mine = [t for t in sent if behavior["id"] in t]
    assert len(mine) == 1 and "Asks again" in mine[0]
    recent = (await client.get(f"{B}/alerts", headers=auth)).json()["alerts"]
    assert recent[0]["delivered"] == ["slack"] and recent[0]["stats"]["hits"] == 1
    bad = await client.patch(
        f"{B}/{behavior['id']}", headers=auth, json={"alert": {"threshold": 0}}
    )
    assert bad.status_code == 422


async def test_promote_and_export_make_eval_examples(client, pool):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    behavior = (
        await client.post(
            f"{B}",
            headers=auth,
            json={
                "name": "Asks again",
                "actor": "user",
                "detector": "rule",
                "rule": {"kind": "repeat_request"},
            },
        )
    ).json()
    trace_id = await _trace(pool, owner)
    await scan.scan_trace(await scan.get_behavior(UUID(behavior["id"])), trace_id)
    hit = (await client.get(f"{B}/{behavior['id']}/hits", headers=auth)).json()["hits"][0]
    await client.post(f"{B}/hits/{hit['id']}/review", headers=auth, json={"verdict": "confirmed"})
    promoted = await client.post(f"{B}/{behavior['id']}/promote", headers=auth)
    assert promoted.status_code == 201, promoted.text
    eval_id = promoted.json()["eval_id"]
    assert promoted.json()["examples"] == 1
    examples = (await client.get(f"/api/v1/intuitions/{eval_id}/examples", headers=auth)).json()
    item = examples[0]["item"]
    assert examples[0]["label"] == "yes" and item["window"] == {"start": 4, "end": 4}
    assert [s["index"] for s in item["steps"]] == [2, 3, 4, 5]
    # A hand-tagged window on a linked behavior feeds the eval too.
    manual = await client.post(
        f"{B}/{behavior['id']}/hits",
        headers=auth,
        json={"trace_id": str(trace_id), "start_idx": 0, "end_idx": 0},
    )
    assert manual.status_code == 201 and manual.json()["source"] == "human"
    exported = await client.post(
        f"{B}/datasets", headers=auth,
        json={"eval_id": eval_id, "label": "no", "windows": [{"trace_id": str(trace_id), "start_idx": 5, "end_idx": 5}]},
    )  # fmt: skip
    assert exported.status_code == 201, exported.text
    examples = (await client.get(f"/api/v1/intuitions/{eval_id}/examples", headers=auth)).json()
    assert sorted(e["label"] for e in examples) == ["no", "yes", "yes"]
    assert (await client.post(f"{B}/{behavior['id']}/promote", headers=auth)).status_code == 422
