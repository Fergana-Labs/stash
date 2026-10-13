"""Real SQL lifecycle with external judges stubbed; no paid inference or GPU work."""

import io
import zipfile
from pathlib import Path
from uuid import UUID

import pypdf

from backend.services.intuition import builder, providers, service

from .test_intuitions import QUESTIONS, _grade_all, _register
from .test_intuitions import fake_jev as fake_jev


async def create(client, auth):
    response = await client.post(
        "/api/v1/intuitions",
        headers=auth,
        json={
            "name": "Output quality",
            "output_type": "choice",
            "description": "Helpful replies",
            "labels": [{"id": "good"}, {"id": "bad"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["model"]["id"]


async def add(client, auth, model_id, examples):
    response = await client.post(
        f"/api/v1/intuitions/{model_id}/builder/examples", headers=auth, json={"examples": examples}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_builder_holdout_calibration_serving_and_correction(client, fake_jev, monkeypatch):
    auth = await _register(client)
    model_id = await create(client, auth)
    rows = await add(
        client,
        auth,
        model_id,
        [
            {
                "item": f"please thanks {i}" if i % 2 == 0 else f"no {i}",
                "label": "good" if i % 2 == 0 else "bad",
                "note": "Be polite",
            }
            for i in range(5)
        ],
    )
    held = [r for r in rows if r["split"] == "eval"]
    assert len(held) == 1
    assert {r["label"] for r in rows if r["split"] == "train"} == {"good", "bad"}
    await add(
        client,
        auth,
        model_id,
        [{"item": "User interview: courtesy matters", "note": "Reference material"}],
    )
    proposed = []

    async def propose(description, output_type, labels, examples, count, guidance):
        proposed.extend(examples)
        assert held[0]["item"] not in [e["item"] for e in examples]
        assert "User interview" in guidance
        assert all(e["note"] == "Be polite" for e in examples)
        return {"rubric": QUESTIONS, "rationale": "Courtesy", "examples_considered": len(examples)}

    monkeypatch.setattr(service, "propose_rubric", propose)
    prepare = await client.post(f"/api/v1/intuitions/{model_id}/builder/prepare", headers=auth)
    assert prepare.status_code == 200, prepare.text
    assert held[0]["id"] not in prepare.json()["draft"]["seed_example_ids"]
    drafted = await client.post(
        f"/api/v1/intuitions/{model_id}/draft/draft-rubric", headers=auth, json={}
    )
    assert drafted.status_code == 200 and len(proposed) == 4
    await client.patch(
        f"/api/v1/intuitions/{model_id}/draft",
        headers=auth,
        json={"rubric": drafted.json()["rubric"]},
    )
    await _grade_all(client, auth, model_id)
    fitted = await client.post(f"/api/v1/intuitions/{model_id}/draft/fit", headers=auth, json={})
    assert fitted.status_code == 200, fitted.text
    assert fitted.json()["metrics"]["eval"]["n"] == 1
    assert fitted.json()["metrics"]["fit_options"]["rows"] == 4
    # One held-out example is limited data, not a regression: the first version saves.
    gate = fitted.json()["gate"]
    assert gate["passed"]
    (size,) = [c for c in gate["checks"] if c["name"] == "held_out_size"]
    assert not size["passed"] and not size["blocking"]
    assert (
        await client.post(f"/api/v1/intuitions/{model_id}/draft/promote", headers=auth, json={})
    ).status_code == 200
    predicted = await client.post(
        f"/api/v1/intuitions/{model_id}/predict",
        headers=auth,
        json={"item": "please help me", "caller": "guardrail"},
    )
    assert predicted.status_code == 200, predicted.text
    calls = (
        await client.get(f"/api/v1/intuitions/{model_id}/predictions?status=all", headers=auth)
    ).json()
    assert calls[0]["input"]["item"] == "please help me" and calls[0]["caller"] == "guardrail"
    correction = await client.post(
        f"/api/v1/intuitions/{model_id}/predictions/{calls[0]['id']}/review",
        headers=auth,
        json={"label": "bad", "note": "Not enough detail"},
    )
    assert correction.status_code == 200, correction.text
    assert correction.json()["example"]["split"] == "train"
    assert correction.json()["example"]["note"] == "Not enough detail"
    # A revised draft must be recalibrated even when its feature names are unchanged.
    edited = await client.patch(
        f"/api/v1/intuitions/{model_id}/draft",
        headers=auth,
        json={"description": "Must also explain the next step"},
    )
    assert edited.json()["draft"]["head_stale"]
    assert (
        await client.post(
            f"/api/v1/intuitions/{model_id}/predict",
            headers=auth,
            json={"item": "please help", "version": "draft"},
        )
    ).status_code == 409
    assert (
        await client.post(
            f"/api/v1/intuitions/{model_id}/predict", headers=auth, json={"item": "please help"}
        )
    ).status_code == 200


async def test_duplicate_holdout_is_never_a_seed(client):
    auth = await _register(client)
    model_id = await create(client, auth)
    rows = await add(
        client,
        auth,
        model_id,
        [{"item": str(i), "label": "good" if i % 2 else "bad"} for i in range(5)],
    )
    held = next(r for r in rows if r["split"] == "eval")
    rows = await add(client, auth, model_id, [{"item": held["item"], "label": held["label"]}])
    assert all(r["split"] == "eval" for r in rows if r["item"] == held["item"])
    response = await client.post(f"/api/v1/intuitions/{model_id}/builder/prepare", headers=auth)
    assert response.status_code == 200
    assert not {r["id"] for r in rows if r["split"] == "eval"} & set(
        response.json()["draft"]["seed_example_ids"]
    )


async def test_builder_owner_scope_and_minimum_data(client):
    owner, other = await _register(client), await _register(client)
    model_id = await create(client, owner)
    assert (
        await client.post(f"/api/v1/intuitions/{model_id}/builder/prepare", headers=other)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/intuitions/{model_id}/builder/prepare", headers=owner)
    ).status_code == 409
    assert (
        await client.get(f"/api/v1/intuitions/{model_id}/predictions?offset=-1", headers=owner)
    ).status_code == 422


async def test_recorded_trace_annotations_are_feedback_not_judge_input(client, pool):
    owner, other = await _register(client), await _register(client)
    model_id, other_model = await create(client, owner), await create(client, other)
    owner_id = await pool.fetchval(
        "SELECT owner_user_id FROM intuition_models WHERE id=$1", UUID(model_id)
    )
    other_id = await pool.fetchval(
        "SELECT owner_user_id FROM intuition_models WHERE id=$1", UUID(other_model)
    )
    trace_id = await pool.fetchval(
        "INSERT INTO rm_traces(owner_user_id,external_id,title,source_format) VALUES($1,'test-trace','Support task','stash') RETURNING id",
        owner_id,
    )
    step_id = await pool.fetchval(
        "INSERT INTO rm_trace_steps(trace_id,idx,role,content) VALUES($1,0,'assistant','Original output') RETURNING id",
        trace_id,
    )
    await pool.execute(
        "INSERT INTO rm_annotations(owner_user_id,trace_id,step_id,rating,comment) VALUES($1,$2,$3,-1,'Give a clear next step'),($4,$2,$3,1,'Other reviewer feedback')",
        owner_id,
        trace_id,
        step_id,
        other_id,
    )
    response = await client.post(
        f"/api/v1/intuitions/{model_id}/builder/trace",
        headers=owner,
        json={"trace_id": str(trace_id), "label": "bad"},
    )
    assert response.status_code == 201, response.text
    example = response.json()[0]
    assert example["note"] == "Step 1: Bad. Give a clear next step"
    assert "annotations" not in example["item"] and "scores" not in example["item"]
    assert example["item"]["steps"][0]["content"] == "Original output"
    forbidden = await client.post(
        f"/api/v1/intuitions/{other_model}/builder/trace",
        headers=other,
        json={"trace_id": str(trace_id), "label": "good"},
    )
    assert forbidden.status_code == 404


async def test_file_inputs_are_read_and_images_have_visible_descriptions(client, monkeypatch):
    auth = await _register(client)
    response = await client.post(
        "/api/v1/intuitions/inputs",
        headers=auth,
        files={"file": ("notes.md", b"User wants clear answers", "text/markdown")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "User wants clear answers"
    calls = []

    async def describe(**kwargs):
        calls.append(kwargs)
        return "A slide with a centered title and crowded body text"

    monkeypatch.setattr(builder.llm, "complete_chat", describe)
    response = await client.post(
        "/api/v1/intuitions/inputs",
        headers=auth,
        files={"file": ("slide.png", b"stub image", "image/png")},
    )
    assert response.status_code == 200
    item = response.json()
    assert item["data_url"].startswith("data:image/png;base64,") and "crowded" in item["content"]
    assert calls[0]["messages"][0]["content"][0]["type"] == "image"
    assert "data_url" not in providers.judge_item(item)
    too_large = await client.post(
        "/api/v1/intuitions/inputs",
        headers=auth,
        files={"file": ("notes.txt", b"a" * (builder.MAX_BYTES + 1), "text/plain")},
    )
    assert too_large.status_code == 422


async def test_pdf_and_slide_deck_text_inputs(monkeypatch):
    # Preserve this interpreter's parser library location in its isolated child.
    monkeypatch.setenv("PYTHONPATH", str(Path(pypdf.__file__).resolve().parents[1]))
    deck = io.BytesIO()
    with zipfile.ZipFile(deck, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Clear slide title</a:t></p:sld>',
        )
    slide = await builder.read_input(deck.getvalue(), "slides.pptx", "application/octet-stream")
    assert slide["content"] == "Clear slide title"
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    stream = pypdf.generic.DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (Readable instructions) Tj ET")
    font = pypdf.generic.DictionaryObject(
        {
            pypdf.generic.NameObject("/Type"): pypdf.generic.NameObject("/Font"),
            pypdf.generic.NameObject("/Subtype"): pypdf.generic.NameObject("/Type1"),
            pypdf.generic.NameObject("/BaseFont"): pypdf.generic.NameObject("/Helvetica"),
        }
    )
    page[pypdf.generic.NameObject("/Resources")] = pypdf.generic.DictionaryObject(
        {
            pypdf.generic.NameObject("/Font"): pypdf.generic.DictionaryObject(
                {pypdf.generic.NameObject("/F1"): font}
            )
        }
    )
    page[pypdf.generic.NameObject("/Contents")] = stream
    document = io.BytesIO()
    writer.write(document)
    pdf = await builder.read_input(document.getvalue(), "instructions.pdf", "application/pdf")
    assert "Readable instructions" in pdf["content"]


async def test_failed_predictions_are_logged_and_history_is_paginated(
    client, fake_jev, monkeypatch
):
    auth = await _register(client)
    # The recorded demo uses cached features and exercises the real serving head.
    loaded = await client.post("/api/v1/intuitions/examples/support-replies", headers=auth)
    assert loaded.status_code == 201, loaded.text
    model_id = loaded.json()["model"]["id"]

    async def failed(*args):
        raise providers.ProviderError("Judge unavailable")

    monkeypatch.setattr(providers, "grade", failed)
    for i in range(3):
        response = await client.post(
            f"/api/v1/intuitions/{model_id}/predict",
            headers=auth,
            json={"item": f"Unseen request {i}"},
        )
        assert response.status_code == 503, response.text
    first = (
        await client.get(
            f"/api/v1/intuitions/{model_id}/predictions?status=all&limit=2", headers=auth
        )
    ).json()
    second = (
        await client.get(
            f"/api/v1/intuitions/{model_id}/predictions?status=all&limit=2&offset=2", headers=auth
        )
    ).json()
    assert len(first) == 2 and len(second) == 2
    assert not {r["id"] for r in first} & {r["id"] for r in second}
    assert first[0]["output"]["error"] == "Judge unavailable"
    assert second[0]["output"]["error"] == "Judge unavailable"
