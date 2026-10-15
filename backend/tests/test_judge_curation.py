# ruff: noqa: F811 -- pytest fixtures imported from test_model_wizard are used as parameters
"""Judge curation: brief, triage, expert queue, calibration links, topics, golden-set health."""

import json

import numpy as np
import pytest

from backend.services import llm
from backend.services.intuition import curation, fusion, providers, spec

from .test_model_wizard import (  # noqa: F401 -- fixtures
    _auth,
    _events,
    _model_with_examples,
    _text,
    _use,
    fakes,
    scripted_claude,
)

MW = "/api/v1/model-wizard"


def test_cohen_kappa_discounts_chance_agreement():
    assert curation.cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    # Always saying "a" agrees 75% of the time with a mostly-"a" rater, but is worth nothing.
    assert curation.cohen_kappa(["a", "a", "a", "b"], ["a", "a", "a", "a"]) == pytest.approx(0.0)
    assert curation.cohen_kappa([], []) is None


def test_kmeans_separates_obvious_clusters():
    rng = np.random.default_rng(1)
    a = rng.normal([5, 0, 0], 0.1, size=(10, 3))
    b = rng.normal([0, 5, 0], 0.1, size=(10, 3))
    X = np.vstack([a, b])
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    assign = curation.kmeans(X, 2)
    assert len(set(assign[:10])) == 1 and len(set(assign[10:])) == 1 and assign[0] != assign[10]


async def _shipped(client, auth) -> str:
    model_id = await _model_with_examples(client, auth)
    assert (await client.post(f"{MW}/models/{model_id}/train", headers=auth)).status_code == 200
    resp = await client.post(
        f"/api/v1/intuitions/{model_id}/draft/promote", headers=auth, json={"force": True}
    )
    assert resp.status_code == 200, resp.text
    return model_id


async def _serve(client, auth, model_id, text) -> str:
    resp = await client.post(
        f"/api/v1/intuitions/{model_id}/predict", headers=auth, json={"item": text}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["prediction_id"]


async def test_brief_tracks_what_a_good_eval_still_needs(client, fakes):
    auth = await _auth(client)
    model_id = await _model_with_examples(client, auth, n=4)
    brief = (await client.get(f"{MW}/models/{model_id}/brief", headers=auth)).json()
    assert not brief["complete"] and "must_never" in brief["missing"]
    resp = await client.patch(
        f"{MW}/models/{model_id}/brief",
        headers=auth,
        json={
            "decision": "Whether a support reply can be sent as is",
            "input": "A drafted reply",
            "labels": [{"id": "send", "means": "Polite and correct", "not": "Merely polite"}],
            "costly_mistake": "Sending a rude reply",
            "must_never": ["A reply that insults the customer"],
        },
    )
    assert resp.status_code == 200 and resp.json()["complete"]
    assert (
        await client.patch(f"{MW}/models/{model_id}/brief", headers=auth, json={"vibes": "x"})
    ).status_code == 422
    # Clearing a field reopens it.
    cleared = (
        await client.patch(f"{MW}/models/{model_id}/brief", headers=auth, json={"must_never": None})
    ).json()
    assert cleared["missing"] == ["must_never"]


async def test_triage_confirms_escalates_and_ignores(client, fakes, monkeypatch):
    auth = await _auth(client)
    model_id = await _shipped(client, auth)
    confirm = await _serve(client, auth, model_id, "please send this thanks")
    escalate = await _serve(client, auth, model_id, "please hmm")
    ignore = await _serve(client, auth, model_id, "lorem ipsum")
    triage = (await client.get(f"{MW}/models/{model_id}/queue/triage", headers=auth)).json()[
        "items"
    ]
    assert {str(r["id"]) for r in triage} == {confirm, escalate, ignore}

    resp = await client.post(
        f"{MW}/models/{model_id}/predictions/{confirm}/triage",
        headers=auth,
        json={"action": "looks_right"},
    )
    assert resp.status_code == 200 and resp.json()["example"]["label"] == "send"
    resp = await client.post(
        f"{MW}/models/{model_id}/predictions/{escalate}/triage",
        headers=auth,
        json={"action": "escalate", "note": "unsure"},
    )
    assert resp.json()["status"] == "escalated"
    assert (
        await client.post(
            f"{MW}/models/{model_id}/predictions/{ignore}/triage",
            headers=auth,
            json={"action": "ignore"},
        )
    ).json()["status"] == "dismissed"
    assert (
        await client.post(
            f"{MW}/models/{model_id}/predictions/{confirm}/triage",
            headers=auth,
            json={"action": "ignore"},
        )
    ).status_code == 409

    expert = (await client.get(f"{MW}/models/{model_id}/queue/expert", headers=auth)).json()[
        "items"
    ]
    assert [str(r["id"]) for r in expert] == [escalate] and expert[0]["status"] == "escalated"
    resp = await client.post(
        f"{MW}/models/{model_id}/predictions/{escalate}/resolve",
        headers=auth,
        json={
            "label": "rewrite",
            "note": "Says please but never answers the question",
            "pin": True,
        },
    )
    assert resp.status_code == 200, resp.text
    golden = resp.json()["example"]
    assert golden["label"] == "rewrite" and golden["pinned"] and golden["source"] == "production"
    detail = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert detail["counts"]["escalated"] == 0 and detail["counts"]["pinned"] == 1

    # The reviewer's reason drives criteria discovery.
    seen = {}

    async def discover(owner_id, mid, count, guidance):
        seen["guidance"] = guidance
        return {"insights": [], "pairs": []}

    monkeypatch.setattr(fusion, "discover_criteria", discover)
    resp = await client.post(
        f"{MW}/models/{model_id}/criteria-from-corrections", headers=auth, json={}
    )
    assert resp.status_code == 200 and resp.json()["reasons"] == 1
    assert "never answers the question" in seen["guidance"]


async def test_calibration_links_are_blind_and_measure_agreement(client, fakes):
    auth = await _auth(client)
    model_id = await _shipped(client, auth)
    link = (
        await client.post(
            f"{MW}/models/{model_id}/review-links", headers=auth, json={"reviewer": "Dana"}
        )
    ).json()
    token = link["token"]

    # No account: the token is the credential, and it never reveals anyone's labels.
    view = (await client.get(f"/api/v1/review-links/{token}")).json()
    assert view["reviewer"] == "Dana" and len(view["items"]) == curation.CALIBRATION_SET
    assert all(i["my_label"] is None and "label" not in i for i in view["items"])
    examples = {
        e["id"]: e
        for e in (await client.get(f"/api/v1/intuitions/{model_id}/examples", headers=auth)).json()
    }
    for n, item in enumerate(view["items"]):
        truth = examples[item["id"]]["label"]
        label = (
            truth if n % 4 else ("send" if truth == "rewrite" else "rewrite")
        )  # disagree on 3 of 12
        resp = await client.post(
            f"/api/v1/review-links/{token}/items/{item['id']}", json={"label": label}
        )
        assert resp.status_code == 200
    assert (
        await client.post(
            f"/api/v1/review-links/{token}/items/{item['id']}", json={"label": "maybe"}
        )
    ).status_code == 422

    agreement = (await client.get(f"{MW}/models/{model_id}/agreement", headers=auth)).json()
    (pair,) = agreement["pairs"]
    assert pair["a"] == "You" and pair["b"] == "Dana" and pair["n"] == 12
    assert pair["agreement"] == pytest.approx(0.75)
    assert len(agreement["disagreements"]) == 3
    assert agreement["judge"]["n"] > 0 and agreement["verdict"]

    await client.delete(f"{MW}/models/{model_id}/review-links/{token}", headers=auth)
    assert (await client.get(f"/api/v1/review-links/{token}")).status_code == 404
    other = await _auth(client)
    assert (await client.get(f"{MW}/models/{model_id}/agreement", headers=other)).status_code == 404


async def test_golden_set_health_flags_duplicates_and_lookalikes(client, fakes):
    auth = await _auth(client)
    model_id = await _model_with_examples(client, auth, n=8)
    await client.post(
        f"/api/v1/intuitions/{model_id}/examples",
        headers=auth,
        json={
            "examples": [
                {"item": "please reply 0 thanks", "label": "send"},
                {"item": "no reply 1 whatever", "label": "send"},
            ]
        },
    )
    health = (await client.get(f"{MW}/models/{model_id}/health", headers=auth)).json()
    assert any(p["similarity"] >= 0.99 for p in health["duplicates"])
    assert any({p["a_label"], p["b_label"]} == {"send", "rewrite"} for p in health["lookalikes"])
    assert any("Nothing is pinned" in i for i in health["issues"])
    assert {c["label"] for c in health["coverage"]} == {"send", "rewrite"}


async def test_topics_cluster_examples_and_traffic(client, fakes, monkeypatch):
    auth = await _auth(client)
    model_id = await _model_with_examples(client, auth)

    async def names(*, prompt, output_model, **_):
        n = prompt.count("CLUSTER ")
        return output_model(
            topics=[{"cluster": i, "name": f"Topic {i}", "description": "d"} for i in range(n)]
        )

    monkeypatch.setattr(llm, "complete_structured", names)
    stats = (await client.post(f"{MW}/models/{model_id}/topics", headers=auth)).json()
    assert len(stats["topics"]) >= 2 and stats["computed_at"]
    assert sum(sum(t["examples"].values()) for t in stats["topics"]) == 24
    assert (await client.get(f"{MW}/models/{model_id}/topics", headers=auth)).json()[
        "topics"
    ] == stats["topics"]


async def test_wizard_saves_the_brief_and_invites_a_reviewer(client, fakes, scripted_claude):
    script, seen = scripted_claude
    auth = await _auth(client)
    model_id = await _model_with_examples(client, auth, n=8)
    session = (
        await client.post(f"{MW}/sessions", headers=auth, json={"model_id": model_id})
    ).json()
    script += [
        [
            _use(
                1,
                "save_brief",
                {"costly_mistake": "Sending a rude reply", "must_never": ["Insults"], "bogus": "x"},
            )
        ],
        [
            _use(
                2,
                "add_examples",
                {"examples": [{"item": "you idiot", "label": "rewrite", "pinned": True}]},
            ),
            _use(3, "invite_reviewer", {"name": "Dana"}),
        ],
        [_text("Share this link with Dana.")],
    ]
    resp = await client.post(
        f"{MW}/sessions/{session['id']}/messages",
        headers=auth,
        json={"text": "Rude replies are the worst"},
    )
    events = _events(resp.text)
    card = next(e for e in events if e["type"] == "card")
    assert card["kind"] == "agreement" and "/review/" in card["props"]["invited"]
    # The wizard sees the brief and what it still lacks.
    assert (
        '"costly_mistake": "Sending a rude reply"' in seen[-1]["system"]
        and '"missing"' in seen[-1]["system"]
    )
    examples = (await client.get(f"/api/v1/intuitions/{model_id}/examples", headers=auth)).json()
    assert [e["item"] for e in examples if e["pinned"]] == ["you idiot"]


async def test_wizard_holds_the_brief_until_the_model_exists(client, fakes, scripted_claude):
    script, seen = scripted_claude
    auth = await _auth(client)
    session = (await client.post(f"{MW}/sessions", headers=auth, json={})).json()
    script += [
        [
            _use(
                1,
                "save_brief",
                {"decision": "Send or rewrite a reply", "costly_mistake": "Sending a rude one"},
            )
        ],
        [_text("Got it. What do the inputs look like?")],
    ]
    await client.post(
        f"{MW}/sessions/{session['id']}/messages", headers=auth, json={"text": "triage replies"}
    )
    assert "held_until_model_exists" in seen[-1]["messages"][-1]["content"][0]["content"]
    assert '"brief_so_far": {"decision": "Send or rewrite a reply"' in seen[-1]["system"]

    # A later turn creates the model; the held brief lands on it, merged with what create_model adds.
    script += [
        [
            _use(
                2,
                "create_model",
                {
                    "name": "Replies",
                    "output_type": "choice",
                    "description": "d",
                    "labels": [
                        {"id": "send", "description": "s"},
                        {"id": "rewrite", "description": "r"},
                    ],
                    "brief": {"input": "A drafted reply"},
                },
            )
        ],
        [_text("Created.")],
    ]
    await client.post(
        f"{MW}/sessions/{session['id']}/messages", headers=auth, json={"text": "drafted replies"}
    )
    stored = (await client.get(f"{MW}/sessions/{session['id']}", headers=auth)).json()
    brief = (await client.get(f"{MW}/models/{stored['model_id']}/brief", headers=auth)).json()[
        "brief"
    ]
    assert brief == {
        "decision": "Send or rewrite a reply",
        "costly_mistake": "Sending a rude one",
        "input": "A drafted reply",
    }
    assert stored["brief"] == {}


async def test_report_falls_back_to_the_live_version_while_the_draft_is_untrained(client, fakes):
    auth = await _auth(client)
    model_id = await _shipped(client, auth)
    report = (await client.get(f"{MW}/models/{model_id}/report", headers=auth)).json()["report"]
    assert report["is_live"] and report["version"] == 1
    # Editing the instructions opens an untrained draft; the live report still shows.
    resp = await client.patch(
        f"/api/v1/intuitions/{model_id}/draft", headers=auth, json={"description": "Stricter"}
    )
    assert resp.status_code == 200, resp.text
    report = (await client.get(f"{MW}/models/{model_id}/report", headers=auth)).json()["report"]
    assert report["is_live"] and report["version"] == 1
    trained = await client.post(f"{MW}/models/{model_id}/train", headers=auth)
    assert trained.status_code == 200, trained.text
    report = (await client.get(f"{MW}/models/{model_id}/report", headers=auth)).json()["report"]
    assert not report["is_live"] and report["version"] == 2


def test_multi_issue_labels_are_canonical_sets():
    from backend.services.intuition.spec import normalize_label

    issues = [{"id": "rude"}, {"id": "long"}]
    assert normalize_label("multi", "item", issues, "rude+long") == "long+rude"
    assert normalize_label("multi", "item", issues, "long, rude") == "long+rude"
    assert normalize_label("multi", "item", issues, "none") == "none"
    with pytest.raises(ValueError, match="Unknown issues"):
        normalize_label("multi", "item", issues, "rude+typo")


async def test_multi_issue_model_trains_and_predicts_a_set(client, fakes, monkeypatch):
    async def grade(version, questions, seeds, item):
        # Jev's zero-shot answer per issue: rude when it says "whatever", verbose when it rambles.
        text = json.dumps(item).lower()
        cue = {"verdict-rude": "whatever", "verdict-verbose": "ramble"}
        return {
            q["id"]: {"type": "noul", "probabilities": {"true": p, "false": 1 - p}}
            for q in questions
            for p in [0.85 if cue.get(q["id"], "\0") in text else 0.15]
        }

    monkeypatch.setattr(providers, "_grade_jev", grade)
    auth = await _auth(client)
    resp = await client.post(
        "/api/v1/intuitions",
        headers=auth,
        json={
            "name": "Reply issues",
            "output_type": "multi",
            "description": "Which issues does the reply have?",
            "labels": [
                {"id": "rude", "description": "Impolite"},
                {"id": "verbose", "description": "Rambles"},
            ],
            "rubric": [],
        },
    )
    assert resp.status_code == 201, resp.text
    model_id = resp.json()["model"]["id"]
    examples = []
    for i in range(24):
        rude, verbose = i % 2 == 1, i % 3 == 0
        text = (
            ("please" if not rude else "whatever")
            + (" verbose verbose ramble" if verbose else "")
            + f" reply {i}"
        )
        label = "+".join(x for x, on in (("rude", rude), ("verbose", verbose)) if on) or "none"
        examples.append(
            {"item": text, "label": label, "split": "eval" if i % 4 in (0, 1) else "train"}
        )
    assert (
        await client.post(
            f"/api/v1/intuitions/{model_id}/examples", headers=auth, json={"examples": examples}
        )
    ).status_code == 201
    report = (await client.post(f"{MW}/models/{model_id}/train", headers=auth)).json()
    assert report["holdout"]["n"] > 0 and report["holdout"]["accuracy"] is not None
    assert {r["name"] for r in report["leaderboard"]} >= {"Jev zero-shot", "Fused model"}
    # The zero-shot signal is one yes/no question per issue.
    detail = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    ids = {q["id"] for q in detail["draft"]["rubric"]}
    assert {"verdict-rude", "verdict-verbose"} <= ids
    out = (
        await client.post(
            f"/api/v1/intuitions/{model_id}/predict",
            headers=auth,
            json={"item": "whatever reply", "version": "draft"},
        )
    ).json()
    assert (
        out["kind"] == "multi"
        and "rude" in out["issues"]
        and set(out["probabilities"]) == {"rude", "verbose"}
    )
    assert out["label"] == "+".join(sorted(out["issues"])) or out["label"] == "none"


async def test_the_brief_is_compiled_into_what_the_judge_reads(client, fakes):
    auth = await _auth(client)
    model_id = await _model_with_examples(client, auth, n=4)
    await client.patch(
        f"{MW}/models/{model_id}/brief",
        headers=auth,
        json={"costly_mistake": "Sending a rude reply", "must_never": ["Insults"]},
    )
    draft = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()["draft"]
    own, brief = draft["description"].split(spec.BRIEF_MARKER)
    assert own == "Would I send it?" and "Sending a rude reply" in brief and "- Insults" in brief
    # Editing the instructions keeps the brief attached; editing the brief rewrites it.
    await client.patch(
        f"/api/v1/intuitions/{model_id}/draft",
        headers=auth,
        json={"description": "Would I send this?"},
    )
    await client.patch(
        f"{MW}/models/{model_id}/brief", headers=auth, json={"must_never": ["Threats"]}
    )
    description = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()[
        "draft"
    ]["description"]
    assert (
        description.startswith("Would I send this?" + spec.BRIEF_MARKER)
        and "Threats" in description
        and "Insults" not in description
    )


async def test_generated_examples_carry_suggestions_until_accepted(client, fakes, monkeypatch):
    auth = await _auth(client)
    model_id = await _model_with_examples(client, auth, n=4)

    async def generated(*, output_model, **_):
        return output_model(
            items=[
                {"item": "please, happy to help", "label": "send", "reason": "Polite and complete"},
                {"item": "figure it out", "label": "nonsense", "reason": "?"},
            ]
        )

    monkeypatch.setattr(llm, "complete_structured", generated)
    resp = await client.post(
        f"/api/v1/intuitions/{model_id}/examples/generate", headers=auth, json={"count": 2}
    )
    assert resp.status_code == 201, resp.text
    made = {e["item"]: e for e in resp.json()}
    assert (
        made["please, happy to help"]["label"] == "send"
        and made["please, happy to help"]["needs_review"]
    )
    assert made["please, happy to help"]["note"] == "Suggested send: Polite and complete"
    assert made["figure it out"]["label"] is None  # an invalid proposal is dropped, not stored
    accepted = (
        await client.post(
            f"/api/v1/intuitions/{model_id}/examples/accept-suggestions", headers=auth
        )
    ).json()
    assert accepted["accepted"] == 1


async def test_wizard_creates_multi_issue_models_with_their_issues(client, fakes, scripted_claude):
    script, _ = scripted_claude
    auth = await _auth(client)
    session = (await client.post(f"{MW}/sessions", headers=auth, json={})).json()
    issues = [
        {"id": "bad_background", "description": "Not white"},
        {"id": "person_in_shot", "description": "A person"},
    ]
    script += [
        [
            _use(
                1,
                "create_model",
                {
                    "name": "Photo rules",
                    "output_type": "multi",
                    "description": "Which rules does it break?",
                    "labels": issues,
                },
            )
        ],
        [
            _use(
                2,
                "add_examples",
                {
                    "examples": [
                        {"item": "kid on a red rug", "label": "person_in_shot+bad_background"}
                    ]
                },
            )
        ],
        [_text("Created.")],
    ]
    events = _events(
        (
            await client.post(
                f"{MW}/sessions/{session['id']}/messages", headers=auth, json={"text": "photos"}
            )
        ).text
    )
    assert not [e for e in events if e["type"] == "activity" and e["status"] == "error"]
    model_id = next(e["model_id"] for e in events if e["type"] == "model")
    detail = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert detail["model"]["output_type"] == "multi" and [
        lab["id"] for lab in (detail["draft"] or detail["active"])["labels"]
    ] == ["bad_background", "person_in_shot"]
    (example,) = (await client.get(f"/api/v1/intuitions/{model_id}/examples", headers=auth)).json()
    assert example["label"] == "bad_background+person_in_shot"
