"""Reward-only creation and promotion; GPU and LLM execution are stubbed."""

import json
from uuid import UUID, uuid4

import pytest

from backend.services.rm import (
    jobs,
    optimization,
)
from backend.services.rm import (
    optimization_policy as policy,
)
from backend.services.rm import (
    optimization_worker as worker,
)

from .test_rm_monitoring import enabled
from .test_rm_precompute import ready

BASE = "/api/v1/rm/optimizations"
METRIC = {
    "name": "Accepted",
    "unit": "0 or 1",
    "direction": "higher",
    "minimum": 0,
    "maximum": 1,
    "regression_tolerance": 0,
}


def cohort(baseline=0.1, candidate=0.8):
    return [
        {"arm": arm, "status": "completed", "reward": value, "outcome": None}
        for arm, value in [("baseline", baseline), ("candidate", candidate)]
        for _ in range(5)
    ]


def test_reward_improvement_promotes_without_external_outcomes():
    report = policy.compare(cohort(), 5)
    assert report["ready"] and report["promote"]
    assert not report["business_guardrail"]
    assert report["reward_change"]["mean"] == pytest.approx(0.7)
    assert policy.compare(cohort(), 5, {})["promote"]


@pytest.mark.parametrize("baseline,candidate", [(0.4, 0.4), (0.8, 0.1)])
def test_equal_or_worse_reward_is_rejected(baseline, candidate):
    report = policy.compare(cohort(baseline, candidate), 5)
    assert report["ready"] and not report["promote"]


@pytest.mark.parametrize("mutation", ["missing", "queued", "invalid", "abandoned"])
def test_incomplete_or_invalid_reward_evidence_never_promotes(mutation):
    runs = cohort()
    if mutation == "missing":
        runs.pop()
    elif mutation == "queued":
        runs[0]["status"] = "queued"
    elif mutation == "invalid":
        runs[0]["reward"] = None
    else:
        runs[0]["status"] = "abandoned"
    assert not policy.compare(runs, 5)["promote"]


def test_existing_explicit_guardrails_still_require_and_check_outcomes():
    runs = cohort()
    assert not policy.compare(runs, 5, METRIC)["ready"]
    for r in runs:
        r["outcome"] = 1 if r["arm"] == "baseline" else 0
    report = policy.compare(runs, 5, METRIC)
    assert report["ready"] and not report["promote"]
    for r in runs:
        r["outcome"] = 1
    assert policy.compare(runs, 5, METRIC)["promote"]


async def test_default_reward_only_api_scores_with_selected_model_and_promotes(
    client, pool, monkeypatch, tmp_path
):
    auth, owner = await enabled(client, pool)
    model, _ = await ready(client, pool, auth)
    response = await client.post(
        BASE,
        headers=auth,
        json={
            "name": "Reward optimization",
            "agent": "support",
            "scope": "default",
            "reward_model_id": str(model),
            "runs_per_arm": 5,
            "max_rounds": 1,
        },
    )
    assert response.status_code == 201, response.text
    program = response.json()
    pid = UUID(program["id"])
    assert program["metric"] is None
    assert await pool.fetchval("SELECT metric FROM rm_optimizations WHERE id=$1", pid) == {}
    assert (await client.get(BASE, headers=auth)).json()[0]["metric"] is None
    await worker.advance(pid)
    rid = await pool.fetchval("SELECT id FROM rm_optimization_rounds WHERE optimization_id=$1", pid)
    proposals = []

    async def propose(snapshot):
        proposals.append(snapshot)
        return worker.Proposal(
            instructions="Verify fitment before quoting.",
            rationale="Match the reward model's criteria.",
        )

    monkeypatch.setattr(worker, "propose", propose)
    await worker.generate(rid)
    assert proposals[0]["objective"]["reward_model_id"] == str(model)
    assert proposals[0]["business_guardrail"] is None
    monkeypatch.setattr(jobs, "job_dir", lambda token: tmp_path / str(token))
    scored = []

    async def remote(module, directory):
        assert module == "rm_worker.modal_runner"
        assert (
            json.loads((directory / "job.json").read_text())["reward_model_key"]
            == "saved/model.tar.gz"
        )
        assert (directory / "score_items.jsonl").read_text() == ""
        [item] = jobs._read_jsonl(directory / "action_score_items.jsonl")
        credit = 0.8 if item["text"] == "candidate" else 0.1
        jobs._write_jsonl(
            directory / "action_scores.jsonl",
            [
                {
                    "trace_id": item["trace_id"],
                    "step_id": item["step_id"],
                    "score": credit,
                    "credit": credit,
                }
            ],
        )
        scored.append(item)

    monkeypatch.setattr(jobs, "run_worker", remote)
    for n in range(10):
        assigned = await client.post(
            f"{BASE}/{pid}/runs",
            headers=auth,
            json={
                "work_key": str(n),
                "agent": "support",
                "scope": "default",
                "agent_version": "agent-1",
            },
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["metric"] is None
        run_id = UUID(assigned.json()["run_id"])
        arm = await pool.fetchval("SELECT arm FROM rm_optimization_runs WHERE id=$1", run_id)
        items = [{"trace_id": str(uuid4()), "step_id": str(uuid4()), "text": arm}]
        await pool.execute(
            "UPDATE rm_optimization_runs SET status='queued',score_items=$2 WHERE id=$1",
            run_id,
            items,
        )
        await worker.score(run_id)
    assert len(scored) == 10
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_optimization_runs WHERE optimization_id=$1 AND outcome IS NOT NULL",
            pid,
        )
        == 0
    )
    await worker.advance(pid)
    data = await optimization.detail(owner, pid)
    assert data["rounds"][0]["status"] == "promoted"
    assert data["active_revision_id"] == data["rounds"][0]["candidate_id"]
    assert data["rounds"][0]["report"]["promote"]
    assert not data["rounds"][0]["report"]["business_guardrail"]
    rejected_outcome = await client.post(
        f"{BASE}/runs/{run_id}/outcome", headers=auth, json={"value": 1, "source": "unused"}
    )
    assert rejected_outcome.status_code == 422
    await worker.advance(pid)
    assert (await optimization.detail(owner, pid))["status"] == "completed"


def test_mcp_begin_defaults_to_reward_and_preserves_explicit_guardrails(monkeypatch):
    from cli import mcp_server

    requests = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def _post(self, path, *, json):
            requests.append((path, json))
            return {"id": "test"}

    monkeypatch.setattr(mcp_server, "_client", Client)
    mcp_server.stash_optimization_begin("Improve", "model", "agent", "default")
    assert requests[-1][1]["reward_model_id"] == "model"
    assert requests[-1][1]["metric"] is None
    mcp_server.stash_optimization_begin(
        "Improve", "model", "agent", "default", metric_name="Accepted"
    )
    assert requests[-1][1]["metric"]["name"] == "Accepted"
