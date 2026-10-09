"""Intuition models: lifecycle, caching, gating, serving, inbox and owner isolation.

The Jev call is replaced by a deterministic fake so tests exercise the real
SQL, cache keys and fitting without network access.
"""

import json

import pytest
from httpx import AsyncClient

from backend.services.intuition import head as heads
from backend.services.intuition import providers

from .conftest import unique_name

QUESTIONS = [
    {"id": "polite", "type": "noul", "prompt": "Is the reply polite?",
     "criteria": {"true": "Polite", "false": "Rude"}},
    {"id": "length", "type": "score", "prompt": "How long is it?",
     "criteria": ["short", "right", "long"]},
]
LABELS = [{"id": "send", "description": "ok"}, {"id": "rewrite", "description": "bad"}]


def _text(item) -> str:
    return json.dumps(item).lower()


@pytest.fixture
def fake_jev(monkeypatch):
    """Answers from item text: 'please' -> polite, word count -> length level."""
    calls = []

    async def grade(version, questions, seeds, item):
        calls.append((item, [q["id"] for q in questions]))
        text = _text(item)
        answers = {}
        for q in questions:
            if q["type"] == "noul":
                p = 0.9 if ("please" in text or "good" in text) else 0.1
                answers[q["id"]] = {"type": "noul", "probabilities": {"true": p, "false": 1 - p}}
            elif q["type"] == "score":
                level = min(len(text.split()) // 4, len(q["criteria"]) - 1)
                probs = {str(i): (0.8 if i == level else 0.2 / (len(q["criteria"]) - 1))
                         for i in range(len(q["criteria"]))}
                answers[q["id"]] = {"type": "score", "probabilities": probs}
            else:
                opts = list(q["criteria"])
                answers[q["id"]] = {"type": "choice",
                                    "probabilities": {o: 1 / len(opts) for o in opts}}
        return answers

    monkeypatch.setattr(providers, "_grade_jev", grade)
    return calls


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/users/register", json={"name": unique_name("im"), "password": "securepassword1"}
    )
    assert resp.status_code == 201
    return _auth(resp.json()["api_key"])


async def _choice_model(client, auth) -> str:
    resp = await client.post("/api/v1/intuitions", headers=auth, json={
        "name": "Replies", "output_type": "choice", "description": "Would I send it?",
        "labels": LABELS, "rubric": QUESTIONS,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["model"]["id"]


def _examples(n: int = 24) -> list[dict]:
    rows = []
    for i in range(n):
        good = i % 2 == 0
        rows.append({
            "item": f"please {i} thanks" if good else f"no {i}",
            "label": "send" if good else "rewrite",
            "split": "eval" if i % 4 in (0, 1) else "train",
        })
    return rows


async def _grade_all(client, auth, model_id):
    for _ in range(20):
        resp = await client.post(f"/api/v1/intuitions/{model_id}/draft/grade", headers=auth, json={})
        assert resp.status_code == 200, resp.text
        if resp.json()["remaining"] == 0:
            return
    raise AssertionError("grading did not converge")


async def test_choice_lifecycle(client: AsyncClient, fake_jev):
    auth = await _register(client)
    model_id = await _choice_model(client, auth)
    resp = await client.post(f"/api/v1/intuitions/{model_id}/examples", headers=auth,
                             json={"examples": _examples()})
    assert resp.status_code == 201, resp.text

    # Fitting before grading is refused with an actionable message.
    resp = await client.post(f"/api/v1/intuitions/{model_id}/draft/fit", headers=auth, json={})
    assert resp.status_code == 409 and "grade" in resp.json()["detail"]

    await _grade_all(client, auth, model_id)
    first_calls = len(fake_jev)
    resp = await client.post(f"/api/v1/intuitions/{model_id}/draft/fit", headers=auth, json={})
    assert resp.status_code == 200, resp.text
    fitted = resp.json()
    assert fitted["metrics"]["eval"]["accuracy"] == 1.0
    assert fitted["gate"]["passed"]
    assert fitted["head"]["feature_names"] == ["polite", "length=0", "length=1", "length=2"]

    resp = await client.post(f"/api/v1/intuitions/{model_id}/draft/promote", headers=auth, json={})
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["active"]["number"] == 1 and detail["draft"] is None

    # Serving a cached item makes no judge call; a new item does, once.
    resp = await client.post(f"/api/v1/intuitions/{model_id}/predict", headers=auth,
                             json={"item": "please 0 thanks", "caller": "test-agent"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["label"] == "send" and len(fake_jev) == first_calls
    resp = await client.post(f"/api/v1/intuitions/{model_id}/predict", headers=auth,
                             json={"item": "absolutely not", "caller": "test-agent"})
    prediction = resp.json()
    assert prediction["label"] == "rewrite" and len(fake_jev) == first_calls + 1
    assert set(prediction["rubric"]) == {"polite", "length"}

    # Adding a rubric question only asks the judge the new question.
    new_q = {"id": "mentions_order", "type": "noul", "prompt": "Mentions an order?",
             "criteria": {"true": "yes", "false": "no"}}
    resp = await client.patch(f"/api/v1/intuitions/{model_id}/draft", headers=auth,
                              json={"rubric": [*QUESTIONS, new_q]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["draft"]["head_stale"] is True
    before = len(fake_jev)
    await _grade_all(client, auth, model_id)
    assert all(qs == ["mentions_order"] for _, qs in fake_jev[before:])

    # A hand-edited head that is worse than the active one fails the gate.
    draft = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()["draft"]
    n_feat = len(draft["feature_names"])
    resp = await client.put(f"/api/v1/intuitions/{model_id}/draft/head", headers=auth,
                            json={"weights": [[0.0] * n_feat, [0.0] * n_feat], "bias": [0, 0]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["gate"]["passed"] is False
    resp = await client.post(f"/api/v1/intuitions/{model_id}/draft/promote", headers=auth, json={})
    assert resp.status_code == 409
    resp = await client.put(f"/api/v1/intuitions/{model_id}/draft/head", headers=auth,
                            json={"weights": [[1.0]], "bias": [0, 0]})
    assert resp.status_code == 422

    # Forced promotion is recorded, and the previous version can be restored.
    resp = await client.post(f"/api/v1/intuitions/{model_id}/draft/promote", headers=auth,
                             json={"force": True})
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["active"]["number"] == 2 and detail["active"]["gate"]["forced"] is True
    v1 = next(v for v in detail["versions"] if v["number"] == 1)
    resp = await client.post(f"/api/v1/intuitions/{model_id}/versions/{v1['id']}/restore", headers=auth)
    assert resp.status_code == 200 and resp.json()["active"]["number"] == 1


async def test_inbox_review_creates_production_example(client: AsyncClient, fake_jev):
    auth = await _register(client)
    model_id = await _choice_model(client, auth)
    await client.post(f"/api/v1/intuitions/{model_id}/examples", headers=auth,
                      json={"examples": _examples()})
    await _grade_all(client, auth, model_id)
    await client.post(f"/api/v1/intuitions/{model_id}/draft/fit", headers=auth, json={})
    await client.post(f"/api/v1/intuitions/{model_id}/draft/promote", headers=auth, json={})
    served = (await client.post(f"/api/v1/intuitions/{model_id}/predict", headers=auth,
                                json={"item": "hmm maybe", "caller": "support-agent"})).json()

    inbox = (await client.get(f"/api/v1/intuitions/{model_id}/predictions", headers=auth)).json()
    assert [p["id"] for p in inbox] == [served["prediction_id"]]
    assert inbox[0]["caller"] == "support-agent"

    resp = await client.post(
        f"/api/v1/intuitions/{model_id}/predictions/{served['prediction_id']}/review",
        headers=auth, json={"label": "send"},
    )
    assert resp.status_code == 200, resp.text
    example = resp.json()["example"]
    assert example["source"] == "production" and example["label"] == "send"
    assert example["item"] == "hmm maybe"
    resp = await client.post(
        f"/api/v1/intuitions/{model_id}/predictions/{served['prediction_id']}/review",
        headers=auth, json={"label": "send"},
    )
    assert resp.status_code == 409
    assert (await client.get(f"/api/v1/intuitions/{model_id}/predictions", headers=auth)).json() == []


async def test_preference_model_learns_from_pairs(client: AsyncClient, fake_jev):
    auth = await _register(client)
    resp = await client.post("/api/v1/intuitions", headers=auth, json={
        "name": "Taste", "output_type": "preference", "description": "Which is better?",
        "rubric": QUESTIONS[:1],
    })
    model_id = resp.json()["model"]["id"]
    pairs = [{"item": f"good {i}", "item_b": f"meh {i}", "label": "a" if i % 2 else "b",
              "split": "eval" if i % 3 == 0 else "train"} for i in range(18)]
    for p in pairs:  # orient so the 'good' item always wins
        if p["label"] == "b":
            p["item"], p["item_b"] = p["item_b"], p["item"]
    resp = await client.post(f"/api/v1/intuitions/{model_id}/examples", headers=auth,
                             json={"examples": pairs})
    assert resp.status_code == 201, resp.text
    bad = await client.post(f"/api/v1/intuitions/{model_id}/examples", headers=auth,
                            json={"examples": [{"item": "x", "item_b": "y", "label": "send"}]})
    assert bad.status_code == 422
    await _grade_all(client, auth, model_id)
    fitted = (await client.post(f"/api/v1/intuitions/{model_id}/draft/fit", headers=auth, json={})).json()
    assert fitted["metrics"]["eval"]["accuracy"] == 1.0
    assert fitted["head"]["weights"][0][0] > 0
    await client.post(f"/api/v1/intuitions/{model_id}/draft/promote", headers=auth, json={})
    resp = await client.post(f"/api/v1/intuitions/{model_id}/compare", headers=auth,
                             json={"item_a": "meh new", "item_b": "good new"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["winner"] == "b" and resp.json()["p_a_wins"] < 0.5


async def test_owner_isolation(client: AsyncClient, fake_jev):
    owner = await _register(client)
    other = await _register(client)
    model_id = await _choice_model(client, owner)
    for method, path in [
        ("GET", ""), ("GET", "/examples"), ("POST", "/draft/grade"), ("POST", "/predict"),
        ("GET", "/predictions"), ("DELETE", ""),
    ]:
        body = {"item": "x"} if path == "/predict" else ({} if method == "POST" else None)
        resp = await client.request(method, f"/api/v1/intuitions/{model_id}{path}", headers=other,
                                    json=body)
        assert resp.status_code == 404, (method, path, resp.status_code)
    listed = (await client.get("/api/v1/intuitions", headers=other)).json()["models"]
    assert listed == []


async def test_demo_loads_without_judge_calls(client: AsyncClient, monkeypatch):
    async def no_calls(*args, **kwargs):
        raise AssertionError("the demo must replay recorded answers")

    monkeypatch.setattr(providers, "_grade_jev", no_calls)
    auth = await _register(client)
    resp = await client.post("/api/v1/intuitions/examples/support-replies", headers=auth)
    assert resp.status_code == 201, resp.text
    detail = resp.json()
    assert detail["active"] is not None and not detail["active"]["head_stale"]
    assert detail["counts"]["inbox"] == 4 and detail["counts"]["ungraded"] == 0
    assert detail["active"]["metrics"]["eval"]["n"] >= 4


def test_head_fit_recovers_signal():
    rows = [{"example_id": str(i), "kind": "item", "f": [0.9 if i % 2 else 0.1], "label": "a" if i % 2 else "b"}
            for i in range(20)]
    head = heads.fit("choice", ["x"], ["a", "b"], rows, 0.005)
    assert heads.evaluate(head, "choice", rows)["accuracy"] == 1.0
    assert head["weights"][0][0] > head["weights"][1][0]
