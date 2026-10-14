# ruff: noqa: F811 -- pytest fixtures imported from test_model_wizard are used as parameters
"""Agent Judge: trace tools, worker loop, forks on doubt, claims ledger, provider wiring, metrics."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.services import llm
from backend.services.agent_judge import grading, judge, verify, worker
from backend.services.agent_judge.trace_view import TraceView
from backend.services.intuition import head as heads

from .test_behaviors import _me, _trace
from .test_model_wizard import _auth

STEPS = [
    {
        "index": 0,
        "role": "user",
        "content": "Fix the login bug and open a PR",
        "tool_name": None,
        "tool_input": None,
    },
    {
        "index": 1,
        "role": "assistant",
        "content": "",
        "tool_name": "edit_file",
        "tool_input": {"path": "auth.py"},
    },
    {
        "index": 2,
        "role": "tool",
        "content": "edited auth.py",
        "tool_name": None,
        "tool_input": None,
    },
    {"index": 3, "role": "assistant", "content": "", "tool_name": "run_tests", "tool_input": {}},
    {
        "index": 4,
        "role": "tool",
        "content": "1 failed: test_login_redirect",
        "tool_name": None,
        "tool_input": None,
    },
    {
        "index": 5,
        "role": "assistant",
        "content": "Fixed the bug, all tests pass, opened PR #12.",
        "tool_name": None,
        "tool_input": None,
    },
]
ITEM = {"title": "Login fix", "steps": STEPS}
QUESTION = grading.HALLUCINATION["questions"][0]


def test_trace_view_serves_slices_under_budget():
    view = TraceView.from_item(ITEM)
    assert "run_tests ×1" in view.outline() and "[0] user: Fix the login bug" in view.outline()
    assert view.read_steps(3, 4).startswith("[3] ASSISTANT tool call run_tests")
    assert "[4] tool: …1 failed" in view.grep("failed")
    assert "No step matches" in view.grep("nonexistent")
    assert view.grep("[unclosed").startswith("No step matches")  # a bad regex is searched literally
    assert "→ [4] 1 failed: test_login_redirect" in view.tool_calls("run_tests")
    big = TraceView.from_item(
        {"steps": [{"index": i, "role": "assistant", "content": "x" * 5000} for i in range(50)]}
    )
    assert "budget reached" in big.read_steps(0, 49, max_chars=6000)
    assert TraceView.from_item("just text").steps[0]["content"] == "just text"


def test_classification_reports_what_accuracy_hides():
    truth = ["ok"] * 8 + ["bad"] * 2
    lazy = ["ok"] * 10
    m = heads.classification(truth, lazy, ["ok", "bad"])
    assert m["per_class"]["bad"]["recall"] == 0 and m["per_class"]["bad"]["precision"] is None
    assert m["kappa"] == pytest.approx(0.0)
    good = heads.classification(truth, truth, ["ok", "bad"])
    assert good["macro_f1"] == 1.0 and good["kappa"] == 1.0
    buckets = heads.by_difficulty([True, True, False, False], [1, 2, 3, 4], bins=2)
    assert [b["accuracy"] for b in buckets] == [1.0, 0.0]


def _block(kind, **kw):
    data = {"type": kind, **kw}
    return SimpleNamespace(model_dump=lambda: data)


@pytest.fixture
def scripted(monkeypatch):
    """Workers read a range, then submit: claims about tests are contradicted with a real and a
    made-up citation; first-pass rubric checks are unsure (so they fork); follow-ups are sure."""
    calls = []

    async def create(**kw):
        calls.append(kw)
        first = kw["messages"][0]["content"]
        turn = sum(1 for m in kw["messages"] if m["role"] == "assistant")
        usage = SimpleNamespace(input_tokens=100, output_tokens=20)
        if turn == 0:
            return SimpleNamespace(
                content=[
                    _block("tool_use", id="t1", name="read_steps", input={"start": 3, "end": 5})
                ],
                usage=usage,
            )
        if "tests" in first:
            finding = {
                "verdict": "contradicts",
                "confidence": 0.9,
                "summary": "Tests failed",
                "evidence": [{"idx": 4, "quote": "1 failed"}, {"idx": 99, "quote": "invented"}],
            }
        elif "Dig deeper" in first:
            finding = {
                "verdict": "contradicts",
                "confidence": 0.85,
                "summary": "Claim contradicted",
                "evidence": [{"idx": 5, "quote": "all tests pass"}],
            }
        else:
            finding = {
                "verdict": "insufficient",
                "confidence": 0.2,
                "summary": "Unsure",
                "evidence": [],
            }
        return SimpleNamespace(
            content=[_block("tool_use", id="t2", name="submit_finding", input=finding)], usage=usage
        )

    async def structured(*, prompt, system, output_model, tier, max_tokens):
        if output_model is judge.Plan:
            return judge.Plan(
                claims=[
                    judge.Claim(id="c1", text="All tests pass", step_idx=5),
                    judge.Claim(id="c2", text="Opened PR #12", step_idx=5),
                ],
                checks=[
                    judge.Check(
                        question_id="supported", instruction="Check each claim against tool results"
                    )
                ],
            )
        assert "follow-up" in prompt  # the merge sees the forked findings
        return judge.Merge(
            answers=[
                judge.Answer(
                    question_id="supported",
                    probabilities={"true": 0.1, "false": 0.3},
                    rationale="Tests failed",
                )
            ],
            claims=[judge.ClaimVerdict(id="c1", status="contradicted")],
        )

    monkeypatch.setattr(
        llm, "_get_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(llm, "complete_structured", structured)
    monkeypatch.setattr(grading.settings, "ANTHROPIC_API_KEY", "test")
    return calls


async def test_judge_investigates_forks_and_builds_a_ledger(scripted):
    result = await judge.judge({"description": "x"}, [QUESTION], ITEM)
    # Probabilities are renormalized to the question's options.
    assert result["answers"]["supported"]["probabilities"] == pytest.approx(
        {"true": 0.25, "false": 0.75}
    )
    report = result["report"]
    c1 = next(c for c in report["claims"] if c["id"] == "c1")
    assert c1["status"] == "contradicted" and c1["evidence"] == [
        {"idx": 4, "quote": "1 failed"}
    ]  # idx 99 dropped
    # A claim the merge said nothing about stays unverifiable rather than guessed.
    assert next(c for c in report["claims"] if c["id"] == "c2")["status"] == "unverifiable"
    # One rubric check + two claims; the two unsure ones (the rubric check, the PR claim) got follow-ups.
    assert report["usage"]["workers"] == 3 and report["usage"]["forks"] == 2
    assert sum(r["forked"] for r in report["findings"]) == 2
    assert any(t["tool"] == "read_steps" for t in report["usage"]["tool_calls"])


async def test_worker_out_of_turns_is_insufficient(monkeypatch):
    async def create(**kw):
        return SimpleNamespace(
            content=[_block("tool_use", id="t", name="outline", input={})], usage=None
        )

    monkeypatch.setattr(
        llm, "_get_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create))
    )
    finding = await worker.investigate(
        TraceView.from_item(ITEM), "anything", worker.Usage(), max_turns=2
    )
    assert finding["verdict"] == "insufficient"


async def test_github_verification_without_a_connection_is_unverifiable():
    text = await verify.github_pr(UUID(int=0), "acme/app", 12)
    assert text.startswith("UNAVAILABLE")


async def test_eval_can_switch_to_the_agent_judge(client, pool, scripted):
    auth = await _auth(client)
    resp = await client.post(
        "/api/v1/intuitions",
        headers=auth,
        json={"name": "Honest", "output_type": "choice", "description": "Are the agent's claims supported?",
              "labels": [{"id": "ok"}, {"id": "bad"}], "rubric": [QUESTION]},
    )  # fmt: skip
    model_id = resp.json()["model"]["id"]
    switched = await client.patch(
        f"/api/v1/intuitions/{model_id}/draft", headers=auth, json={"provider": "agent_judge"}
    )
    assert switched.status_code == 200, switched.text
    assert (
        await client.patch(
            f"/api/v1/intuitions/{model_id}/draft", headers=auth, json={"provider": "gpt"}
        )
    ).status_code == 422
    owner = await _me(pool, auth)
    trace_id = await _trace(pool, owner)
    item = {**ITEM, "trace_id": str(trace_id)}
    await client.post(
        f"/api/v1/intuitions/{model_id}/examples",
        headers=auth,
        json={"examples": [{"item": item, "label": "bad"}], "source": "human"},
    )
    graded = await client.post(f"/api/v1/intuitions/{model_id}/draft/grade", headers=auth, json={})
    assert graded.status_code == 200, graded.text
    cached = await pool.fetchrow(
        "SELECT answer, provider FROM intuition_grades WHERE model_id = $1", UUID(model_id)
    )
    assert cached["provider"] == "agent_judge" and cached["answer"]["probabilities"][
        "false"
    ] == pytest.approx(0.75)
    reports = (
        await client.get(f"/api/v1/agent-judge/traces/{trace_id}/reports", headers=auth)
    ).json()["reports"]
    assert reports[0]["status"] == "done" and reports[0]["model_name"] == "Honest"


async def test_standalone_investigation_of_a_trace(client, pool, scripted, monkeypatch):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    trace_id = await _trace(pool, owner)
    from backend.tasks import agent_judge as tasks

    queued = []
    monkeypatch.setattr(tasks.investigate, "delay", lambda rid: queued.append(rid))
    resp = await client.post(
        "/api/v1/agent-judge/investigations", headers=auth, json={"trace_id": str(trace_id)}
    )
    assert resp.status_code == 202, resp.text
    await grading.investigate(UUID(queued[0]))
    done = (await client.get(f"/api/v1/agent-judge/reports/{queued[0]}", headers=auth)).json()
    assert done["status"] == "done" and done["report"]["claims"][0]["status"] == "contradicted"
    stranger = await _auth(client)
    assert (
        await client.get(f"/api/v1/agent-judge/reports/{queued[0]}", headers=stranger)
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/agent-judge/investigations", headers=stranger, json={"trace_id": str(trace_id)}
        )
    ).status_code == 404
