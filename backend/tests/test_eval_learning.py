"""Eval learning: regression gate, label queue, seed selection, and criteria search."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from backend.services import llm
from backend.services.intuition import improve, selection
from backend.tasks import intuitions as tasks

from .test_intuitions import LABELS, QUESTIONS, _examples, _grade_all, _register
from .test_intuitions import fake_jev as fake_jev

IM = "/api/v1/intuitions"


async def _model(client, auth, rubric) -> str:
    resp = await client.post(
        IM,
        headers=auth,
        json={
            "name": "Replies",
            "output_type": "choice",
            "description": "Would I send it?",
            "labels": LABELS,
            "rubric": rubric,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model"]["id"]


async def _saved(client, auth, rubric=QUESTIONS) -> str:
    model_id = await _model(client, auth, rubric)
    await client.post(f"{IM}/{model_id}/examples", headers=auth, json={"examples": _examples()})
    await _grade_all(client, auth, model_id)
    await client.post(f"{IM}/{model_id}/draft/fit", headers=auth, json={})
    resp = await client.post(f"{IM}/{model_id}/draft/promote", headers=auth, json={"force": True})
    assert resp.status_code == 200, resp.text
    return model_id


async def test_regressions_block_save_until_overridden(client: AsyncClient, fake_jev):
    auth = await _register(client)
    model_id = await _saved(client, auth)
    examples = (await client.get(f"{IM}/{model_id}/examples", headers=auth)).json()
    rewrite = next(e for e in examples if e["label"] == "rewrite" and e["split"] == "train")
    resp = await client.patch(
        f"{IM}/{model_id}/examples/{rewrite['id']}", headers=auth, json={"pinned": True}
    )
    assert resp.status_code == 200 and resp.json()["pinned"] is True

    # A refit of the same criteria keeps every example right: nothing blocks.
    fitted = (await client.post(f"{IM}/{model_id}/draft/fit", headers=auth, json={})).json()
    assert fitted["gate"]["passed"], fitted["gate"]
    names = {c["name"] for c in fitted["gate"]["checks"]}
    assert {"pinned_examples", "no_flips"} <= names

    # A head that always says "send" gets the pinned "rewrite" wrong and flips held-out ones.
    draft = (await client.get(f"{IM}/{model_id}", headers=auth)).json()["draft"]
    n = len(draft["feature_names"])
    gate = (
        await client.put(
            f"{IM}/{model_id}/draft/head",
            headers=auth,
            json={"weights": [[0.0] * n, [0.0] * n], "bias": [5, -5]},
        )
    ).json()["gate"]
    assert not gate["passed"]
    failing = {c["name"] for c in gate["checks"] if not c["passed"] and c["blocking"]}
    assert {"pinned_examples", "no_flips"} <= failing
    assert gate["flips"] and all(f["candidate"] == "send" for f in gate["flips"])
    assert gate["pinned"]["n"] == 1 and gate["pinned"]["accuracy"] == 0

    blocked = await client.post(f"{IM}/{model_id}/draft/promote", headers=auth, json={})
    assert blocked.status_code == 409
    forced = await client.post(f"{IM}/{model_id}/draft/promote", headers=auth, json={"force": True})
    assert forced.status_code == 200 and forced.json()["active"]["gate"]["forced"] is True


async def test_label_queue_ranks_conflicting_outcomes_and_uncertain_calls(
    client: AsyncClient, fake_jev
):
    auth = await _register(client)
    model_id = await _saved(client, auth)

    async def call(item, ref):
        resp = await client.post(
            f"{IM}/{model_id}/predict", headers=auth, json={"item": item, "ref": ref}
        )
        return resp.json()

    confident = await call("please please good thanks", "a")
    await call("please please good thanks", "a-again")  # Same input; listed once.
    unsure = await call("maybe", "b")
    conflicted = await call("please good", "c")
    other = "rewrite" if conflicted["label"] == "send" else "send"
    await client.post(
        f"{IM}/{model_id}/feedback",
        headers=auth,
        json={"ref": "c", "label": other, "source": "outcome"},
    )

    queue = (await client.get(f"{IM}/{model_id}/label-queue", headers=auth)).json()
    assert queue[0]["ref"] == "c" and queue[0]["conflict"]
    assert any("outcome feedback" in reason for reason in queue[0]["reasons"])
    refs = [q["ref"] for q in queue]
    assert len([r for r in refs if r in ("a", "a-again")]) == 1
    by_ref = {q["ref"]: q for q in queue}
    assert by_ref["b"]["uncertainty"] >= by_ref.get("a", by_ref.get("a-again"))["uncertainty"]
    assert unsure["prediction_id"] == by_ref["b"]["prediction_id"]
    assert confident["label"]

    # Reviewed calls leave the queue.
    await client.post(
        f"{IM}/{model_id}/predictions/{queue[0]['prediction_id']}/review",
        headers=auth,
        json={"label": other},
    )
    queue = (await client.get(f"{IM}/{model_id}/label-queue", headers=auth)).json()
    assert "c" not in [q["ref"] for q in queue]


def test_seeds_balance_labels_and_prefer_corrected_examples():
    now = datetime.now(UTC)

    def ex(i, label, source="human", age=0):
        return {
            "id": f"{i:02d}",
            "label": label,
            "source": source,
            "created_at": now - timedelta(days=age),
        }

    train = [ex(i, "send", age=i) for i in range(30)] + [
        ex(40, "rewrite", age=5),
        ex(41, "rewrite", "production", age=50),
    ]
    picked = selection.seeds(train, limit=6)
    labels = [e["label"] for e in picked]
    assert labels.count("rewrite") == 2 and labels.count("send") == 4
    assert picked[0]["id"] == "41"  # A corrected production call comes first.
    assert [e["id"] for e in picked if e["label"] == "send"] == ["00", "01", "02", "03"]


async def test_improve_finds_a_better_question_without_using_held_out_examples(
    client: AsyncClient, fake_jev, monkeypatch
):
    auth = await _register(client)
    # Saved with only the length question, which cannot tell polite from rude replies.
    model_id = await _saved(client, auth, rubric=[QUESTIONS[1]])

    calls = []

    async def fake_claude(*, output_model, **_kwargs):
        calls.append(output_model.__name__)
        draft = output_model.model_fields
        polite = {
            "id": "polite",
            "type": "noul",
            "prompt": "Is the reply polite?",
            "criteria": [
                {"key": "true", "description": "Polite"},
                {"key": "false", "description": "Rude"},
            ],
        }
        vague = {
            "id": "vibe",
            "type": "choice",
            "prompt": "What is the vibe?",
            "criteria": [
                {"key": "calm", "description": "Calm"},
                {"key": "busy", "description": "Busy"},
            ],
        }
        if "question" in draft:
            return output_model.model_validate(
                {"rationale": "Mistakes are rude", "question": polite}
            )
        return output_model.model_validate({"rationale": "Fresh", "questions": [vague]})

    monkeypatch.setattr(llm, "complete_structured", fake_claude)
    dispatched = []
    monkeypatch.setattr(tasks.improve, "delay", lambda job_id: dispatched.append(job_id))

    resp = await client.post(f"{IM}/{model_id}/improve", headers=auth)
    assert resp.status_code == 202, resp.text
    assert (await client.post(f"{IM}/{model_id}/improve", headers=auth)).status_code == 409

    graded_before = len(fake_jev)
    await improve.run(dispatched[0])
    job = (await client.get(f"{IM}/{model_id}/improve", headers=auth)).json()["job"]
    assert job["status"] == "succeeded", job["error"]
    result = job["result"]
    assert result["changed"] and result["winner"] == "add_question"
    by_name = {c["name"]: c for c in result["candidates"]}
    assert by_name["add_question"]["cv_log_loss"] < by_name["current"]["cv_log_loss"]
    assert by_name["add_question"]["new_questions"] == ["Is the reply polite?"]

    # Candidates were scored on calibration examples only.
    examples = (await client.get(f"{IM}/{model_id}/examples", headers=auth)).json()
    train = [e for e in examples if e["split"] == "train" and e["label"]]
    assert by_name["current"]["rows"] == len(train)
    held_items = {e["item"] for e in examples if e["split"] == "eval"}
    # The losing "vibe" question exists only during the search, so every item it was
    # asked about was used to choose; none of them may be held out.
    vibe_items = {item for item, questions in fake_jev[graded_before:] if "vibe" in questions}
    assert vibe_items and not vibe_items & held_items

    detail = (await client.get(f"{IM}/{model_id}", headers=auth)).json()
    assert [q["id"] for q in detail["draft"]["rubric"]] == ["length", "polite"]
    assert not detail["draft"]["head_stale"]
    assert result["gate"]["passed"]
    assert (
        await client.post(f"{IM}/{model_id}/draft/promote", headers=auth, json={})
    ).status_code == 200


async def test_improve_requires_a_saved_eval(client: AsyncClient, fake_jev):
    auth = await _register(client)
    model_id = await _model(client, auth, QUESTIONS)
    resp = await client.post(f"{IM}/{model_id}/improve", headers=auth)
    assert resp.status_code == 409
    assert (await client.get(f"{IM}/{model_id}/improve", headers=auth)).json() == {"job": None}
