# ruff: noqa: F811 -- pytest fixtures imported from test_model_wizard are used as parameters
"""Test sets: cases, runs scored by expected answers and evals, and regressions against a baseline."""

from uuid import UUID

import pytest

from backend.services.test_sets import scoring, service
from backend.tasks import test_sets as tasks

from .test_behaviors import STEPS, _me, _trace
from .test_judge_curation import _shipped
from .test_model_wizard import _auth, fakes  # noqa: F401 -- fixture

T = "/api/v1/test-sets"


@pytest.fixture
def queued(monkeypatch):
    runs = []
    monkeypatch.setattr(tasks.score_run, "delay", lambda run_id: runs.append(run_id))
    return runs


@pytest.fixture
def matcher(monkeypatch):
    """The expected-answer judge: an answer matches when it contains the expected text."""

    async def match(case, output):
        ok = case["expected"].lower() in output.lower()
        return {
            "scorer": "expected",
            "passed": ok,
            "reason": "same answer" if ok else "different answer",
        }

    monkeypatch.setattr(scoring, "match_expected", match)


async def _set_with_cases(client, auth, name="Support") -> dict:
    created = await client.post(T, headers=auth, json={"name": name})
    assert created.status_code == 201, created.text
    set_id = created.json()["id"]
    cases = [
        {
            "name": "refund window",
            "input": "Can I return headphones after 5 days?",
            "expected": "30 days",
        },
        {
            "name": "order status",
            "input": [{"role": "user", "content": "Where is order 9120?"}],
            "expected": "UPS",
        },
        {"name": "no reference", "input": "Say hi"},
    ]
    added = await client.post(f"{T}/{set_id}/cases", headers=auth, json={"cases": cases})
    assert added.status_code == 201, added.text
    return (await client.get(f"{T}/{set_id}", headers=auth)).json()


async def _run(client, auth, s, answers: dict[str, str], queued, label="") -> dict:
    by_name = {c["name"]: c["id"] for c in s["cases"]}
    outputs = [{"case_id": by_name[n], "output": a} for n, a in answers.items()]
    resp = await client.post(
        f"{T}/{s['id']}/runs", headers=auth, json={"label": label, "outputs": outputs}
    )
    assert resp.status_code == 202, resp.text
    await service.score_run(UUID(queued[-1]))
    return (await client.get(f"{T}/runs/{resp.json()['id']}", headers=auth)).json()


async def test_runs_compare_with_the_baseline_and_gate_on_regressions(client, queued, matcher):
    auth = await _auth(client)
    s = await _set_with_cases(client, auth)
    first = await _run(
        client,
        auth,
        s,
        {
            "refund window": "Returns are accepted within 30 days.",
            "order status": "It shipped with FedEx.",
            "no reference": "hi",
        },
        queued,
        "v1",
    )
    assert first["status"] == "done"
    assert (
        first["summary"]["passed"] == 2
        and first["summary"]["baseline"] is None
        and first["summary"]["gate"] == "pass"
    )
    second = await _run(
        client,
        auth,
        s,
        {
            "refund window": "No refunds, sorry.",
            "order status": "Shipped with UPS.",
            "no reference": "hello",
        },
        queued,
        "v2",
    )
    summary = second["summary"]
    names = {r["case_id"]: r["case_name"] for r in second["results"]}
    assert [names[c] for c in summary["broke"]] == ["refund window"]
    assert [names[c] for c in summary["fixed"]] == ["order status"]
    assert summary["gate"] == "fail" and summary["baseline"]["pass_rate"] == pytest.approx(2 / 3)
    broken = next(r for r in second["results"] if r["case_name"] == "refund window")
    assert broken["baseline_passed"] is True and broken["scores"][0]["reason"] == "different answer"
    # A failed run never becomes the baseline: the next run still compares with v1.
    again = await _run(
        client,
        auth,
        s,
        {"refund window": "30 days", "order status": "UPS", "no reference": "hi"},
        queued,
        "v3",
    )
    assert again["baseline_run_id"] == first["id"] and again["summary"]["broke"] == []
    # Allowing one regression lets the same run shape pass.
    await client.patch(
        f"{T}/{s['id']}", headers=auth, json={"max_regressions": 1, "baseline_run_id": first["id"]}
    )
    third = await _run(
        client,
        auth,
        s,
        {"refund window": "No refunds.", "order status": "UPS", "no reference": "hi"},
        queued,
    )
    assert third["baseline_run_id"] == first["id"] and third["summary"]["gate"] == "pass"


async def test_eval_scorer_uses_pass_labels(client, fakes, queued):
    auth = await _auth(client)
    model_id = await _shipped(client, auth)
    bad = await client.post(
        T, headers=auth, json={"name": "Tone", "scorers": [{"type": "eval", "eval_id": model_id}]}
    )
    assert bad.status_code == 422  # pass labels are required
    created = (
        await client.post(
            T,
            headers=auth,
            json={
                "name": "Tone",
                "scorers": [{"type": "eval", "eval_id": model_id, "pass_labels": ["send"]}],
            },
        )
    ).json()
    await client.post(
        f"{T}/{created['id']}/cases",
        headers=auth,
        json={
            "cases": [
                {"name": "a", "input": "reply to the customer"},
                {"name": "b", "input": "reply"},
            ]
        },
    )
    s = (await client.get(f"{T}/{created['id']}", headers=auth)).json()
    run = await _run(client, auth, s, {"a": "please, here you go, thanks", "b": "whatever"}, queued)
    results = {r["case_name"]: r for r in run["results"]}
    assert results["a"]["passed"] and not results["b"]["passed"]
    assert results["b"]["scores"][0]["label"] == "rewrite"
    # Scoring a test never shows up as production traffic.
    calls = (await client.get(f"/api/v1/intuitions/{model_id}/predictions", headers=auth)).json()
    assert all(
        p.get("caller") != "test"
        for p in (calls if isinstance(calls, list) else calls.get("predictions", []))
    )


async def test_cases_from_traces_and_validation(client, pool, queued):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    s = (await client.post(T, headers=auth, json={"name": "From prod"})).json()
    trace_id = await _trace(pool, owner)
    first = await client.post(
        f"{T}/{s['id']}/cases/from-trace", headers=auth, json={"trace_id": str(trace_id)}
    )
    assert first.status_code == 201, first.text
    assert first.json()["input"] == STEPS[0][1] and first.json()["expected"] == STEPS[3][1]
    # Up to the second user turn: the history is the input, with a corrected expected answer.
    later = (
        await client.post(
            f"{T}/{s['id']}/cases/from-trace",
            headers=auth,
            json={
                "trace_id": str(trace_id),
                "upto_idx": 4,
                "expected": "Refunds are allowed within 30 days.",
            },
        )
    ).json()
    assert [m["role"] for m in later["input"]] == ["user", "assistant", "user"] and later[
        "expected"
    ].startswith("Refunds are allowed")
    stranger = await _auth(client)
    assert (await client.get(f"{T}/{s['id']}", headers=stranger)).status_code == 404
    assert (
        await client.post(
            f"{T}/{s['id']}/runs",
            headers=auth,
            json={"outputs": [{"case_id": str(UUID(int=1)), "output": "x"}]},
        )
    ).status_code == 422
    assert (await client.post(T, headers=auth, json={"name": "From prod"})).status_code == 422
    resolved = (await client.get(f"{T}/resolve/From prod", headers=auth)).json()
    assert resolved["id"] == s["id"] and len(resolved["cases"]) == 2


def test_compare_without_a_baseline_passes_the_gate():
    results = [
        {
            "case_id": "a",
            "scores": [{"scorer": "expected", "passed": False, "reason": ""}],
            "passed": False,
        }
    ]
    summary = service.compare(results, None, 0)
    assert (
        summary["gate"] == "pass"
        and summary["pass_rate"] == 0
        and summary["scorers"] == {"expected": 0.0}
    )


def test_a_case_that_could_not_be_scored_neither_breaks_nor_counts_as_fixed():
    results = [
        {"case_id": "a", "scores": [], "passed": False, "error": "Scoring failed: X"},
        {"case_id": "b", "scores": [], "passed": True, "error": None},
    ]
    summary = service.compare(results, {"a": True, "b": False}, 0)
    assert summary["broke"] == [] and summary["fixed"] == ["b"] and summary["gate"] == "pass"
    assert summary["errors"] == 1


async def test_resolve_by_a_name_with_a_slash_and_edit_validation(client, queued):
    auth = await _auth(client)
    s = (await client.post(T, headers=auth, json={"name": "QA a/b"})).json()
    resolved = await client.get(f"{T}/resolve/QA%20a%2Fb", headers=auth)
    assert resolved.status_code == 200 and resolved.json()["id"] == s["id"]
    other = (await client.post(T, headers=auth, json={"name": "Other"})).json()
    assert (
        await client.patch(f"{T}/{other['id']}", headers=auth, json={"name": "QA a/b"})
    ).status_code == 422
    case = (
        await client.post(f"{T}/{s['id']}/cases", headers=auth, json={"cases": [{"input": "hi"}]})
    ).json()["cases"][0]
    assert (
        await client.patch(f"{T}/{s['id']}/cases/{case['id']}", headers=auth, json={"input": " "})
    ).status_code == 422
