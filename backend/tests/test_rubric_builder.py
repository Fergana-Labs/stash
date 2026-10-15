# ruff: noqa: F811 -- pytest fixtures imported from test_model_wizard are used as parameters
"""Rubric Builder passes, production cohorts, and criteria mined from users' reactions."""

from uuid import UUID

import pytest

from backend.services import llm
from backend.services.intuition import mining, rubric_builder, service
from backend.tasks import intuitions as tasks

from .test_behaviors import LABELS, _me, _trace
from .test_judge_curation import _shipped
from .test_model_wizard import _auth, fakes  # noqa: F401 -- fixtures

EVALS = "/api/v1/intuitions"

NEW = service._QuestionDraft(
    id="mentions_reply",
    type="noul",
    prompt="Does the message mention a reply?",
    criteria=[
        service._Criterion(key="true", description="Yes"),
        service._Criterion(key="false", description="No"),
    ],
)


def _proposal(keep: list[dict], add: bool = True) -> rubric_builder.Proposal:
    drafts = [
        service._QuestionDraft(
            id=q["id"],
            type=q["type"],
            prompt=q["prompt"],
            criteria=[service._Criterion(key=k, description=v) for k, v in q["criteria"].items()],
        )
        for q in keep
        if q["type"] not in ("eval", "probe")  # signals are kept by apply(), not proposed
    ]
    return rubric_builder.Proposal(
        edits=[
            rubric_builder.Edit(
                kind="add_criterion", question_id="mentions_reply", rationale="Misses replies"
            )
        ],
        questions=drafts + ([NEW] if add else []),
    )


def test_apply_keeps_unchanged_questions_identical():
    current = [
        {
            "id": "polite",
            "type": "noul",
            "prompt": "Is it polite?",
            "criteria": {"true": "Polite", "false": "Rude"},
        }
    ]
    out = rubric_builder.apply(current, _proposal(current))
    assert out[0] is current[0]  # same dict, so its cached answers are reused
    assert out[1]["id"] == "mentions_reply" and out[1]["type"] == "noul"


async def _start(client, auth, model_id, monkeypatch) -> str:
    queued = []
    monkeypatch.setattr(tasks.refine, "delay", lambda job_id: queued.append(job_id))
    resp = await client.post(f"{EVALS}/{model_id}/refine", headers=auth)
    assert resp.status_code == 202, resp.text
    # Only one improvement or refinement runs at a time.
    assert (await client.post(f"{EVALS}/{model_id}/refine", headers=auth)).status_code == 409
    return queued[0]


async def test_refine_stops_when_edits_stop_helping(client, fakes, monkeypatch):
    auth = await _auth(client)
    model_id = await _shipped(client, auth)
    proposals = []

    async def propose(version, errors, production, contradicted, history, judges=None):
        proposals.append(history)
        return _proposal(version["rubric"])

    monkeypatch.setattr(rubric_builder, "propose", propose)
    job_id = await _start(client, auth, model_id, monkeypatch)
    await rubric_builder.run(UUID(job_id))
    job = (await client.get(f"{EVALS}/{model_id}/refine", headers=auth)).json()["job"]
    assert job["status"] == "succeeded", job["error"]
    result = job["result"]
    # The added question carries no new signal under the fake judge: two rejected passes, then stop.
    assert result["passes"] == rubric_builder.PATIENCE and not result["changed"]
    assert [p["accepted"] for p in result["curve"]] == [True, False, False]
    assert result["curve"][0]["cv_accuracy"] == 1.0 and result["curve"][0]["macro_f1"] == 1.0
    # Later passes see what was tried before.
    assert proposals[1][1]["edits"][0]["kind"] == "add_criterion"


async def test_refine_keeps_a_better_rubric_and_drafts_it(client, fakes, monkeypatch):
    auth = await _auth(client)
    model_id = await _shipped(client, auth)
    real = rubric_builder.out_of_fold

    def scored(output_type, rubric, labels, rows):
        out = real(output_type, rubric, labels, rows)
        if any(
            q["id"] == "mentions_reply" for q in rubric
        ):  # pretend it explains the labels better
            out["cv_log_loss"] -= 0.05
        return out

    calls = []

    def judged(rubric):
        return [q["id"] for q in rubric if not rubric_builder.is_signal(q)]

    async def propose(version, errors, production, contradicted, history, judges=None):
        calls.append(judged(version["rubric"]))
        return _proposal(version["rubric"], add="mentions_reply" not in judged(version["rubric"]))

    monkeypatch.setattr(rubric_builder, "out_of_fold", scored)
    monkeypatch.setattr(rubric_builder, "propose", propose)
    job_id = await _start(client, auth, model_id, monkeypatch)
    await rubric_builder.run(UUID(job_id))
    result = (await client.get(f"{EVALS}/{model_id}/refine", headers=auth)).json()["job"]["result"]
    assert result["changed"] and [p["accepted"] for p in result["curve"]][:2] == [True, True]
    assert result["gate"] is not None and result["held_out"]["n"] > 0
    detail = (await client.get(f"{EVALS}/{model_id}", headers=auth)).json()
    start = calls[0]
    assert judged(detail["draft"]["rubric"]) == start + ["mentions_reply"]
    # The next pass started from the accepted rubric.
    assert calls[1] == start + ["mentions_reply"]


FRUSTRATED = [
    ("user", "Find the refund policy for order 88", None),
    ("assistant", "Refunds are not possible for that order.", None),
    ("user", "That's wrong, it was bought last week", None),
    ("assistant", "Refunds are allowed within 30 days.", None),
]
FRUSTRATED_LABELS = {
    "0": {"actor": "user", "intent": "new_request", "sentiment": "neutral", "verdict": "none"},
    "1": {
        "actor": "agent",
        "type": "output",
        "is_output": True,
        "outcome": "answer",
        "stance": "asserted",
    },
    "2": {"actor": "user", "intent": "correction", "sentiment": "negative", "verdict": "rejected"},
    "3": {
        "actor": "agent",
        "type": "output",
        "is_output": True,
        "outcome": "answer",
        "stance": "asserted",
    },
}
HAPPY_LABELS = {
    "0": {"actor": "user", "intent": "new_request", "sentiment": "neutral", "verdict": "none"},
    "1": {
        "actor": "agent",
        "type": "output",
        "is_output": True,
        "outcome": "answer",
        "stance": "asserted",
    },
    "2": {
        "actor": "user",
        "intent": "acknowledgment",
        "sentiment": "positive",
        "verdict": "confirmed",
    },
}


async def test_cohorts_and_criteria_mined_from_reactions(client, pool, monkeypatch, fakes):
    auth = await _auth(client)
    owner = await _me(pool, auth)
    await _trace(pool, owner, steps=FRUSTRATED, labels=FRUSTRATED_LABELS, title="Bad refund")
    await _trace(
        pool,
        owner,
        steps=FRUSTRATED[:2] + [("user", "thanks!", None)],
        labels=HAPPY_LABELS,
        title="Good",
    )
    await _trace(pool, owner, labels=LABELS)
    by = (
        await client.get("/api/v1/behaviors/cohorts", headers=auth, params={"by": "satisfaction"})
    ).json()
    rates = {c["key"]: c["traces"] for c in by["cohorts"]}
    assert rates == {"frustrated": 2, "satisfied": 1}
    frustrated = next(c for c in by["cohorts"] if c["key"] == "frustrated")
    assert frustrated["correction_rate"] == 1.0 and frustrated["frustrated_rate"] == 1.0
    assert (
        await client.get("/api/v1/behaviors/cohorts", headers=auth, params={"by": "vibes"})
    ).status_code == 422

    seen = []

    async def structured(*, prompt, system, output_model, tier, max_tokens):
        seen.append(prompt)
        return mining.Mined(
            rationale="Users push back on refusals that ignore purchase dates", questions=[NEW]
        )

    monkeypatch.setattr(llm, "complete_structured", structured)
    model_id = await _shipped(client, auth)
    resp = await client.post(
        f"{EVALS}/{model_id}/mine-production",
        headers=auth,
        json={"by": "satisfaction", "key": "frustrated"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cohort"]["traces"] == 2 and body["votes"] >= 2
    assert body["examples"][0]["agent_said"] == "Refunds are not possible for that order."
    assert body["examples"][0]["user_replied"].startswith("That's wrong")
    assert body["questions"][0]["id"] == "mentions_reply"
    assert "Refunds are not possible" in seen[0]
    empty = await client.post(
        f"{EVALS}/{model_id}/mine-production",
        headers=auth,
        json={"by": "satisfaction", "key": "satisfied"},
    )
    assert empty.status_code == 409


@pytest.mark.parametrize(
    ("candidate", "best", "expected"),
    [
        ({"cv_log_loss": 0.3}, {"cv_log_loss": 0.4}, True),
        ({"cv_log_loss": 0.398}, {"cv_log_loss": 0.4}, False),
        ({"cv_log_loss": None}, {"cv_log_loss": 0.4}, False),
    ],
)
def test_only_real_gains_are_kept(candidate, best, expected):
    assert rubric_builder.better(candidate, best) is expected


def test_apply_never_turns_signals_into_criteria():
    criterion = {
        "id": "polite",
        "type": "noul",
        "prompt": "Is it polite?",
        "criteria": {"true": "Polite", "false": "Rude"},
    }
    verdict = {
        "id": "verdict",
        "type": "choice",
        "prompt": "Which label fits?",
        "criteria": {"a": "A", "b": "B"},
    }
    probe = {
        "id": "embedding_probe",
        "type": "probe",
        "prompt": "Learned from your labeled examples: which of them does this item most resemble?",
        "criteria": {"a": "A", "b": "B"},
        "version_id": "p1",
    }
    echoed = service._QuestionDraft(
        id="embedding_probe",
        type="noul",
        prompt=probe["prompt"],
        criteria=[
            service._Criterion(key="true", description="A"),
            service._Criterion(key="false", description="B"),
        ],
    )
    proposal = _proposal([criterion, verdict], add=False)
    proposal.questions.append(echoed)
    out = rubric_builder.apply([criterion, verdict, probe], proposal)
    assert [q["id"] for q in out] == ["polite", "verdict", "embedding_probe"]
    assert out[1] is verdict and out[2] is probe
