"""Automatic updates use real SQL and cached judge features; no paid inference."""

from uuid import UUID

import pytest

from backend.services.intuition import providers, service, updates

from .test_eval_builder import add, create
from .test_intuitions import QUESTIONS, _register
from .test_intuitions import fake_jev as fake_jev


@pytest.fixture
def rubric(monkeypatch):
    calls = []

    async def propose(*args, **kwargs):
        calls.append(args)
        return {"rubric": QUESTIONS, "rationale": "Politeness", "examples_considered": 2}

    monkeypatch.setattr(service, "propose_rubric", propose)
    return calls


async def due(pool, model_id):
    await pool.execute(
        "UPDATE intuition_updates SET run_after=now()-interval '1 second' WHERE model_id=$1",
        UUID(model_id),
    )


async def bootstrap(client, pool):
    auth = await _register(client)
    model_id = await create(client, auth)
    response = await client.post(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    assert response.status_code == 200
    assert response.json()["state"] == "needs_examples"
    rows = await add(
        client,
        auth,
        model_id,
        [{"item": "please help", "label": "good"}, {"item": "no way", "label": "bad"}],
    )
    await due(pool, model_id)
    await updates.run(UUID(model_id))
    result = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert result["active"] is not None, (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()
    assert result["active"]["metrics"]["eval"]["n"] == 0
    return auth, model_id, rows, result


async def test_debounce_and_owner_boundary(client, pool):
    auth = await _register(client)
    model_id = await create(client, auth)
    await client.post(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    await add(client, auth, model_id, [{"item": "good", "label": "good"}])
    first = (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()
    await add(client, auth, model_id, [{"item": "bad", "label": "bad"}])
    second = (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()
    assert second["revision"] == first["revision"] + 1
    assert second["run_after"] >= first["run_after"]
    await updates.run(UUID(model_id))
    assert (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()[
        "active"
    ] is None
    remaining = await pool.fetchval(
        "SELECT extract(epoch FROM run_after-now()) FROM intuition_updates WHERE model_id=$1",
        UUID(model_id),
    )
    assert 55 <= remaining <= 60
    other = await _register(client)
    assert (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=other)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/intuitions/{model_id}/builder/updates/retry", headers=other)
    ).status_code == 404


async def test_two_labels_bootstrap_and_new_examples_reuse_rubric_and_features(
    client, pool, fake_jev, rubric
):
    auth, model_id, _, first = await bootstrap(client, pool)
    assert len(rubric) == 1
    original_calls = len(fake_jev)
    await add(
        client,
        auth,
        model_id,
        [
            {"item": "please thanks a new output", "label": "good"},
            {"item": "not labeled yet", "label": None, "needs_review": True},
        ],
    )
    await due(pool, model_id)
    await updates.run(UUID(model_id))
    second = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert second["active"]["number"] == first["active"]["number"] + 1
    assert len(rubric) == 1
    assert len(fake_jev) == original_calls + 1
    assert second["active"]["rubric"] == first["active"]["rubric"]
    assert second["active"]["metrics"]["eval"]["n"] == 1
    assert (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()["state"] == "idle"
    count = len(fake_jev)
    await updates.run(UUID(model_id))
    assert len(fake_jev) == count


async def test_usage_corrections_schedule_head_only_update(client, pool, fake_jev, rubric):
    auth, model_id, _, first = await bootstrap(client, pool)
    prediction = await client.post(
        f"/api/v1/intuitions/{model_id}/predict",
        headers=auth,
        json={"item": "please another reply", "caller": "agent"},
    )
    assert prediction.status_code == 200
    before = len(fake_jev)
    review = await client.post(
        f"/api/v1/intuitions/{model_id}/predictions/{prediction.json()['prediction_id']}/review",
        headers=auth,
        json={"label": "bad", "note": "Incomplete"},
    )
    assert review.status_code == 200
    assert (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()["state"] == "pending"
    await due(pool, model_id)
    await updates.run(UUID(model_id))
    result = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert result["active"]["number"] == first["active"]["number"] + 1
    assert len(rubric) == 1
    assert len(fake_jev) == before


async def test_changed_inputs_cannot_publish_old_update(
    client, pool, fake_jev, rubric, monkeypatch
):
    auth, model_id, rows, first = await bootstrap(client, pool)
    await client.patch(
        f"/api/v1/intuitions/{model_id}/examples/{rows[0]['id']}",
        headers=auth,
        json={"note": "Changed"},
    )
    original_fit = service.fit

    async def edit_during_fit(*args, **kwargs):
        result = await original_fit(*args, **kwargs)
        await client.patch(
            f"/api/v1/intuitions/{model_id}/examples/{rows[1]['id']}",
            headers=auth,
            json={"note": "Changed during update"},
        )
        return result

    monkeypatch.setattr(service, "fit", edit_during_fit)
    await due(pool, model_id)
    await updates.run(UUID(model_id))
    result = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert result["active"]["id"] == first["active"]["id"]
    assert (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()["state"] == "pending"
    monkeypatch.setattr(service, "fit", original_fit)
    await due(pool, model_id)
    await updates.run(UUID(model_id))
    result = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert result["active"]["number"] == first["active"]["number"] + 1


async def test_instruction_change_regenerates_criteria(client, pool, fake_jev, rubric):
    auth, model_id, _, _ = await bootstrap(client, pool)
    await client.patch(
        f"/api/v1/intuitions/{model_id}/draft",
        headers=auth,
        json={"description": "Check completeness"},
    )
    await due(pool, model_id)
    await updates.run(UUID(model_id))
    result = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert result["active"]["description"] == "Check completeness"
    assert len(rubric) == 2


async def test_failures_retry_and_do_not_replace_serving_version(
    client, pool, fake_jev, rubric, monkeypatch
):
    auth, model_id, _, first = await bootstrap(client, pool)
    await add(client, auth, model_id, [{"item": "new input", "label": "bad"}])

    async def unavailable(*args, **kwargs):
        raise providers.ProviderError("Judge unavailable")

    monkeypatch.setattr(providers, "_grade_jev", unavailable)
    for _ in range(3):
        await due(pool, model_id)
        await updates.run(UUID(model_id))
    state = (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()
    assert state["state"] == "failed"
    assert "Judge unavailable" in state["error"]
    result = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert result["active"]["id"] == first["active"]["id"]
    retry = await client.post(f"/api/v1/intuitions/{model_id}/builder/updates/retry", headers=auth)
    assert retry.json()["state"] == "pending"


async def test_reconciliation_dispatches_once_and_recovers_failed_dispatch(
    client, pool, monkeypatch
):
    from backend.tasks import eval_updates

    auth = await _register(client)
    model_id = await create(client, auth)
    await client.post(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    await add(
        client, auth, model_id, [{"item": "good", "label": "good"}, {"item": "bad", "label": "bad"}]
    )
    await due(pool, model_id)
    calls = []
    monkeypatch.setattr(eval_updates.update_eval, "delay", lambda mid: calls.append(mid))
    await eval_updates.reconcile_async()
    await eval_updates.reconcile_async()
    assert calls == [model_id]
    assert (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()["state"] == "queued"
    await pool.execute(
        "UPDATE intuition_updates SET started_at=now()-interval '16 minutes' WHERE model_id=$1",
        UUID(model_id),
    )
    await eval_updates.reconcile_async()
    assert calls == [model_id, model_id]
    await pool.execute(
        "UPDATE intuition_updates SET state='pending' WHERE model_id=$1", UUID(model_id)
    )

    def unavailable(_):
        raise RuntimeError("Broker unavailable")

    monkeypatch.setattr(eval_updates.update_eval, "delay", unavailable)
    with pytest.raises(RuntimeError, match="Broker unavailable"):
        await eval_updates.reconcile_async()
    assert (
        await client.get(f"/api/v1/intuitions/{model_id}/builder/updates", headers=auth)
    ).json()["state"] == "pending"


async def test_reference_changes_regenerate_criteria(client, pool, fake_jev, rubric):
    auth, model_id, _, _ = await bootstrap(client, pool)
    references = await add(
        client,
        auth,
        model_id,
        [
            {
                "item": "Refund policy",
                "label": None,
                "needs_review": True,
                "note": "Reference material",
            }
        ],
    )
    await due(pool, model_id)
    await updates.run(UUID(model_id))
    assert len(rubric) == 2
    assert "Refund policy" in rubric[-1][-1]
    reference = next(e for e in references if e["label"] is None)
    response = await client.delete(
        f"/api/v1/intuitions/{model_id}/examples/{reference['id']}", headers=auth
    )
    assert response.status_code == 204
    await due(pool, model_id)
    await updates.run(UUID(model_id))
    assert len(rubric) == 3
    assert "Refund policy" not in rubric[-1][-1]
