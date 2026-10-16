# ruff: noqa: F811 -- pytest fixtures imported from test_model_wizard are used as parameters
"""Templates, release comparisons, root-cause triage, task types, staleness, and the judge's lookups."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from backend.services import llm
from backend.services.agent_judge import lookups
from backend.services.behaviors import releases, scan, segments, task_types, templates, triage
from backend.services.behaviors.search import quote
from backend.services.intuition import monitoring
from backend.tasks import behaviors as behavior_tasks
from backend.tasks import embeddings as embedding_tasks

from .test_behaviors import LABELS, _me, _trace, segment_embedder  # noqa: F401 -- fixture
from .test_model_wizard import _auth

B = "/api/v1/behaviors"


def test_quote_picks_the_matching_sentence_without_prefixes():
    text = '[0] USER\nHi there. Can I get a refund for order 8841?\n\n[1] ASSISTANT tool call search_kb {"q": 1}\n[]'
    assert quote(text, "refund order") == "Can I get a refund for order 8841?"


def test_release_significance_needs_enough_traces():
    assert not releases.significant(1, 3, 2, 3)
    assert releases.significant(5, 100, 40, 100)
    lo, hi = releases.wilson(5, 100)
    assert lo < 0.05 < hi


async def test_templates_install_as_model_detected_behaviors(client):
    auth = await _auth(client)
    listed = (await client.get(f"{B}/templates", headers=auth)).json()["templates"]
    assert {t["slug"] for t in listed} == set(templates.BY_SLUG)
    created = await client.post(f"{B}/templates/pii-leak", headers=auth)
    assert created.status_code == 201 and created.json()["detector"] == "agent_judge"
    assert (await client.post(f"{B}/templates/complaint", headers=auth)).json()["detector"] == "llm"
    assert (await client.post(f"{B}/templates/nope", headers=auth)).status_code == 404


async def test_release_compare_before_and_after(client, pool):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    behavior = (
        await client.post(
            B,
            headers=auth,
            json={
                "name": "Asks again",
                "actor": "user",
                "detector": "rule",
                "rule": {"kind": "repeat_request"},
            },
        )
    ).json()
    b = await scan.get_behavior(UUID(behavior["id"]))
    now = datetime.now(UTC)
    for days_ago, labels in [(3, LABELS), (2, LABELS), (2, {}), (1, {})]:
        t = await _trace(pool, owner, labels=labels)
        await pool.execute(
            "UPDATE rm_traces SET created_at = $2 WHERE id = $1", t, now - timedelta(days=days_ago)
        )
        await scan.scan_trace(b, t)
    release = (
        await client.post(
            f"{B}/releases",
            headers=auth,
            json={
                "label": "v2 prompt",
                "released_at": (now - timedelta(days=2, hours=12)).isoformat(),
            },
        )
    ).json()
    assert [
        r["label"] for r in (await client.get(f"{B}/releases", headers=auth)).json()["releases"]
    ] == ["v2 prompt"]
    cmp = (
        await client.get(
            f"{B}/{behavior['id']}/compare", headers=auth, params={"release_id": release["id"]}
        )
    ).json()
    assert cmp["before"] == {"traces": 1, "with_hit": 1, "rate": 1.0, "ci": cmp["before"]["ci"]}
    assert cmp["after"]["traces"] == 3 and cmp["after"]["with_hit"] == 1
    assert cmp["change"] == pytest.approx(1 / 3 - 1) and cmp["significant"] is False
    stranger = await _auth(client)
    assert (
        await client.get(
            f"{B}/{behavior['id']}/compare", headers=stranger, params={"release_id": release["id"]}
        )
    ).status_code == 404
    assert (
        await client.delete(f"{B}/releases/{release['id']}", headers=stranger)
    ).status_code == 404
    assert (await client.delete(f"{B}/releases/{release['id']}", headers=auth)).status_code == 204


async def test_triage_groups_hits_into_root_causes(client, pool, monkeypatch):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    behavior = (
        await client.post(
            B,
            headers=auth,
            json={
                "name": "Asks again",
                "actor": "user",
                "detector": "rule",
                "rule": {"kind": "repeat_request"},
            },
        )
    ).json()
    b = await scan.get_behavior(UUID(behavior["id"]))
    for _ in range(2):
        await scan.scan_trace(b, await _trace(pool, owner))
    queued = []
    monkeypatch.setattr(behavior_tasks.triage, "delay", lambda tid: queued.append(tid))

    async def structured(*, prompt, system, output_model, tier, max_tokens):
        assert "HIT 1" in prompt and "steps 5–5" in prompt
        return triage.Triage(
            summary="Empty knowledge-base results are answered as refusals.",
            root_causes=[
                triage.Cause(
                    title="KB search misses return policy",
                    explanation="search_kb returns []",
                    hits=[triage.Cited(hit=0), triage.Cited(hit=1), triage.Cited(hit=9)],
                )
            ],
            suggested_fixes=["Retry with a broader query before answering"],
        )

    monkeypatch.setattr(llm, "complete_structured", structured)
    started = await client.post(f"{B}/{behavior['id']}/triage", headers=auth)
    assert started.status_code == 202
    await triage.run(UUID(queued[0]))
    done = (await client.get(f"{B}/{behavior['id']}/triage", headers=auth)).json()["triage"]
    assert done["status"] == "done"
    cause = done["result"]["root_causes"][0]
    assert (
        cause["share"] == 1.0 and len(cause["traces"]) == 2
    )  # the out-of-range citation is dropped
    assert done["result"]["suggested_fixes"] == ["Retry with a broader query before answering"]


async def test_alert_starts_a_triage(client, pool, monkeypatch):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    behavior = (
        await client.post(
            B,
            headers=auth,
            json={
                "name": "Asks again",
                "actor": "user",
                "detector": "rule",
                "rule": {"kind": "repeat_request"},
                "alert": {"threshold": 1},
            },
        )
    ).json()
    await scan.scan_trace(await scan.get_behavior(UUID(behavior["id"])), await _trace(pool, owner))
    queued = []
    monkeypatch.setattr(behavior_tasks.triage, "delay", lambda tid: queued.append(tid))
    from backend.services.behaviors import alerts

    async def deliver(behavior, text):
        return []

    monkeypatch.setattr(alerts, "deliver", deliver)
    await alerts.evaluate()
    recent = (await client.get(f"{B}/alerts", headers=auth)).json()["alerts"]
    assert recent[0]["triage_id"] is not None and str(recent[0]["triage_id"]) in queued


async def test_task_types_cluster_and_name_requests(client, pool, monkeypatch, segment_embedder):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    for text in [
        "refund for order 1",
        "refund for order 2",
        "refund my order please",
        "fix the login bug",
        "fix the failing login test",
        "fix bug in login",
    ]:
        await _trace(
            pool, owner, steps=[("user", text, None), ("assistant", "ok", None)], labels=None
        )

    async def structured(*, prompt, system, output_model, tier, max_tokens):
        return task_types._Names(
            names=[
                "Refund Requests" if "refund" in prompt.split("CLUSTER 1")[0] else "bug fixes",
                "other",
            ]
        )

    monkeypatch.setattr(llm, "complete_structured", structured)
    cohorts = (await client.get(f"{B}/cohorts", headers=auth, params={"by": "task_type"})).json()[
        "cohorts"
    ]
    assert sum(c["traces"] for c in cohorts) == 6 and len(cohorts) == 2
    assert all(c["key"] == c["key"].lower() for c in cohorts)
    # New traces join the nearest named cluster without renaming.
    await _trace(
        pool,
        owner,
        steps=[("user", "refund order 9 please", None), ("assistant", "ok", None)],
        labels=None,
    )
    assert await task_types.refresh(owner) == 1


async def test_staleness_explains_why_a_rubric_needs_refining(monkeypatch):
    async def version(_):
        return {"metrics": {"eval": {"accuracy": 0.9}}}

    monkeypatch.setattr(monitoring.service, "_load_version", version)
    now = datetime.now(UTC)
    rows = [
        {"truth": "a", "predicted": "a" if i < 4 else "b", "created_at": now, "error": False}
        for i in range(10)
    ]
    drift = {"labels": [{"label": "b", "train_share": 0.1, "recent_share": 0.6}], "features": []}
    result = await monitoring.staleness({"active_version_id": None}, rows, drift)
    assert result["refine_suggested"]
    assert "40%" in result["refine_reason"] and "'b' is now 60%" in result["refine_reason"]
    calm = await monitoring.staleness(
        {"active_version_id": None}, rows[:3], {"labels": [], "features": []}
    )
    assert calm == {"refine_suggested": False, "refine_reason": None}


async def test_eval_alert_rule_validation(client):
    auth = await _auth(client)
    model = (
        await client.post(
            "/api/v1/intuitions",
            headers=auth,
            json={
                "name": "E",
                "output_type": "choice",
                "description": "x",
                "labels": [{"id": "ok"}, {"id": "bad"}],
                "rubric": [],
            },
        )
    ).json()["model"]["id"]
    set_ = await client.put(
        f"/api/v1/intuitions/{model}/alert", headers=auth, json={"min_agreement": 0.75}
    )
    assert set_.status_code == 200 and set_.json()["alert"]["min_agreement"] == 0.75
    assert (
        await client.put(
            f"/api/v1/intuitions/{model}/alert", headers=auth, json={"min_agreement": 2}
        )
    ).status_code == 422


async def test_judge_lookups_find_similar_traces_and_prior_verdicts(client, pool, segment_embedder):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    here = await _trace(pool, owner)
    other = await _trace(pool, owner, title="Another refund")
    for t in (here, other):
        await segments.sync(t, owner)
    while await embedding_tasks._reconcile_trace_segments():
        pass
    await pool.execute(
        """INSERT INTO agent_judge_reports (owner_user_id, trace_id, item_hash, status, report)
           VALUES ($1, $2, 'x', 'done', $3)""",
        owner, other, {"claims": [{"text": "Refunds are not possible", "status": "contradicted"}]},
    )  # fmt: skip
    similar = await lookups.similar_traces(owner, "refund policy order", here)
    assert str(other) in similar and str(here) not in similar
    prior = await lookups.prior_labels(owner, "refund policy order", here)
    assert "earlier judge found “Refunds are not possible” contradicted" in prior
    assert (await lookups.similar_traces(None, "x", None)).startswith("Unavailable")


async def test_judge_sources_tool_reads_through_the_vfs_and_revokes_its_key(client, pool):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    out = await lookups.sources(owner, "ls /")
    assert out and "Traceback" not in out
    live = await pool.fetchval(
        "SELECT count(*) FROM user_api_keys WHERE user_id = $1 AND name LIKE 'agent judge%' AND revoked_at IS NULL",
        owner,
    )
    assert live == 0
    assert (await lookups.sources(owner, "")).startswith("Give a shell script")
