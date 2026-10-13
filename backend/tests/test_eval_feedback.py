"""Eval feedback and monitoring: references, multi-source truth, learning, drift."""

from httpx import AsyncClient

from backend.services.intuition import providers

from .test_intuitions import _choice_model, _examples, _grade_all, _register
from .test_intuitions import fake_jev as fake_jev


async def _served_model(client: AsyncClient, auth: dict) -> str:
    model_id = await _choice_model(client, auth)
    await client.post(
        f"/api/v1/intuitions/{model_id}/examples", headers=auth, json={"examples": _examples()}
    )
    await _grade_all(client, auth, model_id)
    await client.post(f"/api/v1/intuitions/{model_id}/draft/fit", headers=auth, json={})
    resp = await client.post(
        f"/api/v1/intuitions/{model_id}/draft/promote", headers=auth, json={"force": True}
    )
    assert resp.status_code == 200, resp.text
    return model_id


async def _predict(client, auth, model_id, item, ref=None):
    resp = await client.post(
        f"/api/v1/intuitions/{model_id}/predict",
        headers=auth,
        json={"item": item, "ref": ref, "metadata": {"channel": "email"}},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_feedback_by_ref_keeps_every_signal_and_learns_once(client: AsyncClient, fake_jev):
    auth = await _register(client)
    model_id = await _served_model(client, auth)
    served = await _predict(client, auth, model_id, "please help thanks", ref="ticket-1")
    assert served["label"] == "send"
    feedback = f"/api/v1/intuitions/{model_id}/feedback"

    # A delayed outcome arrives by the caller's own reference.
    resp = await client.post(
        feedback,
        headers=auth,
        json={"ref": "ticket-1", "label": "rewrite", "value": 0.0, "source": "outcome"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["prediction_id"] == served["prediction_id"]
    assert resp.json()["example"] is None

    # A human then confirms the original call and teaches it.
    resp = await client.post(
        feedback,
        headers=auth,
        json={"prediction_id": served["prediction_id"], "label": "send", "learn": True},
    )
    assert resp.status_code == 201, resp.text
    example = resp.json()["example"]
    assert example["label"] == "send" and example["source"] == "production"

    # Learning again relabels the same example rather than duplicating it.
    resp = await client.post(
        feedback,
        headers=auth,
        json={"ref": "ticket-1", "label": "rewrite", "learn": True},
    )
    assert resp.json()["example"]["id"] == example["id"]
    examples = (await client.get(f"/api/v1/intuitions/{model_id}/examples", headers=auth)).json()
    assert sum(e["item"] == "please help thanks" for e in examples) == 1

    calls = (
        await client.get(f"/api/v1/intuitions/{model_id}/predictions?status=all", headers=auth)
    ).json()
    (call,) = [c for c in calls if c["id"] == served["prediction_id"]]
    assert call["ref"] == "ticket-1" and call["metadata"] == {"channel": "email"}
    assert call["status"] == "labeled"
    assert [f["source"] for f in call["feedback"]] == ["human", "human", "outcome"]


async def test_feedback_validation(client: AsyncClient, fake_jev, monkeypatch):
    auth = await _register(client)
    model_id = await _served_model(client, auth)
    served = await _predict(client, auth, model_id, "no thanks")
    feedback = f"/api/v1/intuitions/{model_id}/feedback"
    pid = served["prediction_id"]

    assert (
        await client.post(feedback, headers=auth, json={"prediction_id": pid, "label": "maybe"})
    ).status_code == 422
    assert (
        await client.post(
            feedback, headers=auth, json={"prediction_id": pid, "ref": "x", "value": 1}
        )
    ).status_code == 422
    assert (
        await client.post(feedback, headers=auth, json={"prediction_id": pid})
    ).status_code == 422
    assert (
        await client.post(
            feedback, headers=auth, json={"prediction_id": pid, "value": 1, "learn": True}
        )
    ).status_code == 422
    assert (
        await client.post(feedback, headers=auth, json={"ref": "unknown", "label": "send"})
    ).status_code == 404

    async def broken(*_args, **_kwargs):
        raise providers.ProviderError("down", retryable=True)

    monkeypatch.setattr(providers, "_grade_jev", broken)
    failed = await client.post(
        f"/api/v1/intuitions/{model_id}/predict",
        headers=auth,
        json={"item": "never graded before", "ref": "failed"},
    )
    assert failed.status_code == 502
    resp = await client.post(feedback, headers=auth, json={"ref": "failed", "label": "send"})
    assert resp.status_code == 409

    other = await _register(client)
    assert (
        await client.post(feedback, headers=other, json={"prediction_id": pid, "label": "send"})
    ).status_code == 404


async def test_monitoring_measures_against_feedback_truth(client: AsyncClient, fake_jev):
    auth = await _register(client)
    model_id = await _served_model(client, auth)
    feedback = f"/api/v1/intuitions/{model_id}/feedback"
    right = await _predict(client, auth, model_id, "please good", ref="a")
    wrong = await _predict(client, auth, model_id, "no reply", ref="b")
    await _predict(client, auth, model_id, "please again", ref="c")  # no feedback

    await client.post(feedback, headers=auth, json={"ref": "a", "label": right["label"]})
    other = "send" if wrong["label"] == "rewrite" else "rewrite"
    # Outcome says the call was right, but the human correction outranks it.
    await client.post(
        feedback, headers=auth, json={"ref": "b", "label": wrong["label"], "source": "outcome"}
    )
    await client.post(feedback, headers=auth, json={"ref": "b", "label": other, "value": 0.25})

    resp = await client.get(f"/api/v1/intuitions/{model_id}/monitoring", headers=auth)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    summary = data["summary"]
    assert summary["calls"] == 3 and summary["errors"] == 0
    assert summary["with_feedback"] == 2 and summary["accuracy"] == 0.5
    assert summary["mean_value"] == 0.25
    assert 0 <= summary["ece"] <= 1 and summary["reliability"]
    assert len(data["daily"]) == 1 and data["daily"][0]["calls"] == 3
    assert [v["version"] for v in data["versions"]] == [1]

    (miss,) = data["disagreements"]
    assert miss["ref"] == "b" and miss["truth"] == other and miss["truth_source"] == "human"
    assert miss["predicted"] == wrong["label"]
    assert miss["top_feature"]["feature"]

    drift = data["drift"]
    assert drift["recent_calls"] == 3 and drift["version"] == 1
    assert {row["label"] for row in drift["labels"]} == {"send", "rewrite"}
    assert drift["features"] and all("shift" in f for f in drift["features"])


async def test_monitoring_without_calls(client: AsyncClient, fake_jev):
    auth = await _register(client)
    model_id = await _choice_model(client, auth)
    data = (await client.get(f"/api/v1/intuitions/{model_id}/monitoring", headers=auth)).json()
    assert data["summary"]["calls"] == 0 and data["summary"]["accuracy"] is None
    assert data["daily"] == [] and data["drift"] is None
