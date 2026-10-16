"""Native product boundaries. Remote model calls are replaced at the transport seam."""

import base64
import json
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from backend.auth import create_api_key
from backend.services import taste
from backend.services.intuition import history_bridge
from backend.tasks import taste as taste_tasks
from scripts.website_taste import evidence
from scripts.website_taste.activation_spec import SPEC
from scripts.website_taste.probe_pipeline import REPRESENTATION


async def user(client, pool):
    response = await client.post(
        "/api/v1/users/register",
        json={"name": "taste_" + uuid4().hex[:12], "password": "securepassword1"},
    )
    assert response.status_code == 201
    owner = UUID(response.json()["id"])
    await pool.execute("UPDATE users SET reward_models_enabled=true WHERE id=$1", owner)
    key = await create_api_key(owner, name="test", access="full")
    return owner, {"Authorization": "Bearer " + key}


def bundle(tmp_path):
    from scripts.website_taste.corpus import digest

    png = tmp_path / "one.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nexample")
    item = evidence.packet("A website", {"steps": [], "coverage": {"complete": False}}, png)
    item["supervision"] = {
        "label": "disliked",
        "partition": "train",
        "human_reviewed": False,
        "label_source": "explicit_feedback_auto",
        "quote": "Remove the cards",
        "group": "one",
        "provenance": {"reference_image": False},
    }
    dataset = {
        "examples": [item],
        "heldout_status": "previously_inspected_test",
        "label_policy": "automatic_exploratory",
        "source_experiment": "example",
    }
    dataset["sha256"] = digest(json.dumps(dataset, sort_keys=True))
    taste.write(tmp_path / "evidence.json", dataset)
    probe = {
        "version": "temporary",
        "kind": "frozen-multimodal-activation-probe",
        "spec": SPEC,
        "representation": REPRESENTATION,
        "dataset": dataset["sha256"],
        "head": {"dimensions": 2, "weights": [1.0, 0.0], "center": [0.0, 0.0], "bias": 0.0},
        "release_gate": {"passed": False, "checks": {"fresh_human_holdout": False}},
        "metrics": {},
        "limitations": [],
    }
    probe.pop("version")
    probe["version"] = digest(json.dumps(probe, sort_keys=True))
    taste.write(tmp_path / "activation-probe.json", probe)
    return item, probe


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    monkeypatch.setattr(history_bridge, "status", AsyncMock(return_value={"connected": False}))


async def test_workspace_identity_idempotent_and_no_cross_account_evidence(client, pool, tmp_path):
    owner, headers = await user(client, pool)
    first = await client.post("/api/v1/taste", headers=headers)
    assert first.status_code == 200
    second = await client.post("/api/v1/taste", headers=headers)
    assert first.json()["id"] == second.json()["id"]
    item, _ = bundle(tmp_path)
    await pool.execute(
        "UPDATE taste_workspaces SET config=$2 WHERE owner_user_id=$1",
        owner,
        {"probe": str(tmp_path)},
    )
    found = await client.get("/api/v1/taste", headers=headers)
    assert len(found.json()["examples"]) == 1
    _, other = await user(client, pool)
    assert (await client.get("/api/v1/taste", headers=other)).json() is None
    assert (
        await client.get("/api/v1/taste/images/example/" + item["id"], headers=other)
    ).status_code == 404
    assert (
        await client.patch(
            "/api/v1/taste/examples/" + item["id"], headers=other, json={"label": "liked"}
        )
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/taste/jobs", headers=headers, json={"operation": "build", "output": "/etc"}
        )
    ).status_code == 422


async def test_review_is_saved_without_changing_frozen_grader_and_blocks_optimizers(
    client, pool, tmp_path, monkeypatch
):
    owner, headers = await user(client, pool)
    await client.post("/api/v1/taste", headers=headers)
    item, probe = bundle(tmp_path)
    await pool.execute(
        "UPDATE taste_workspaces SET config=$2 WHERE owner_user_id=$1",
        owner,
        {"probe": str(tmp_path)},
    )
    result = await client.patch(
        "/api/v1/taste/examples/" + item["id"],
        headers=headers,
        json={"label": "liked", "note": "The density works"},
    )
    assert result.status_code == 200
    out = result.json()
    assert out["examples"][0]["reviewed"] and out["examples"][0]["label"] == "liked"
    assert out["grader"]["version"] == probe["version"] and out["revision"] == 1
    assert (
        taste.read(tmp_path / "evidence.json")["examples"][0]["supervision"]["label"] == "disliked"
    )
    dispatch = []
    monkeypatch.setattr(taste_tasks.run, "delay", lambda *a: dispatch.append(a))
    monkeypatch.setenv("TASTE_CLOUD_ENABLED", "1")
    for op in ("gepa", "weights", "evaluate"):
        response = await client.post("/api/v1/taste/jobs", headers=headers, json={"operation": op})
        assert response.status_code == 409
    assert dispatch == []


async def test_runtime_uses_same_probe_pixels_and_saves_exact_version(
    client, pool, tmp_path, monkeypatch
):
    owner, headers = await user(client, pool)
    await client.post("/api/v1/taste", headers=headers)
    _, model = bundle(tmp_path)
    await pool.execute(
        "UPDATE taste_workspaces SET config=$2 WHERE owner_user_id=$1",
        owner,
        {"probe": str(tmp_path), "budget": str(tmp_path)},
    )
    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("TASTE_CLOUD_ENABLED", "1")
    seen = []

    def score(self, packet):
        seen.append(packet)
        return {"label": "liked", "score": 0.51, "reward": self.identity, "input_id": packet["id"]}

    from scripts.website_taste.probe_pipeline import ProbeScorer

    monkeypatch.setattr(ProbeScorer, "score_packet", score)
    response = await client.post(
        "/api/v1/taste/predict",
        headers=headers,
        json={
            "brief": "Make a website",
            "trace": [{"id": "1", "role": "user", "text": "Build it with api_key=SECRET"}],
            "screenshot_base64": base64.b64encode(b"\x89PNG\r\n\x1a\npixels").decode(),
            "html": "<html>Current source</html>",
        },
    )
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["version"] == model["version"] and not out["optimization_ready"]
    assert "SECRET" not in json.dumps(seen[0])
    assert seen[0]["input"]["source"]["text"] == "<html>Current source</html>"
    assert seen[0]["image_file"] and seen[0]["input"]["render"]["available"]
    stored = await pool.fetchrow(
        "SELECT * FROM taste_predictions WHERE id=$1", UUID(out["prediction_id"])
    )
    assert stored["version"] == model["version"] and stored["input"] == seen[0]["input"]
    binding = await taste.bind_wizard(owner)
    alias = await client.post(
        f"/api/v1/intuitions/{binding['model_id']}/predict",
        headers=headers,
        json={
            "item": {
                "brief": "Make a website",
                "trace": [{"id": "1", "role": "user", "text": "Current task"}],
                "screenshot_base64": base64.b64encode(b"\x89PNG\r\n\x1a\npixels").decode(),
                "html": "<html>Current source</html>",
            }
        },
    )
    assert alias.status_code == 200, alias.text
    assert alias.json()["version"] == model["version"]


async def test_job_dispatch_is_durable_single_flight_and_cloud_disabled(client, pool, monkeypatch):
    _, headers = await user(client, pool)
    await client.post("/api/v1/taste", headers=headers)
    dispatch = []
    monkeypatch.setattr(taste_tasks.run, "delay", lambda *a: dispatch.append(a))
    response = await client.post(
        "/api/v1/taste/jobs", headers=headers, json={"operation": "discover"}
    )
    assert response.status_code == 202
    assert (
        await client.post("/api/v1/taste/jobs", headers=headers, json={"operation": "discover"})
    ).status_code == 409
    assert len(dispatch) == 1
    monkeypatch.delenv("TASTE_CLOUD_ENABLED", raising=False)
    assert (
        await client.post("/api/v1/taste/jobs", headers=headers, json={"operation": "skill"})
    ).status_code == 409


async def test_comparison_rejects_mismatched_prompts_and_persists_human_choice(
    client, pool, monkeypatch
):
    owner, headers = await user(client, pool)
    await client.post("/api/v1/taste", headers=headers)
    a, b = "a" * 64, "b" * 64
    rows = [
        {"id": a, "task": "one", "brief": "Build a website", "image": True},
        {"id": b, "task": "two", "brief": "Other", "image": True},
    ]
    monkeypatch.setattr(taste, "trials", lambda _: rows)
    req = {"a": a, "b": b, "winner": a}
    assert (
        await client.post("/api/v1/taste/comparisons", headers=headers, json=req)
    ).status_code == 422
    rows[1].update(task="one", brief="Build a website")
    assert (
        await client.post("/api/v1/taste/comparisons", headers=headers, json=req)
    ).status_code == 200
    saved = (await taste.workspace(owner))["reviews"]
    assert next(iter(saved.values()))["winner"] == a
    assert (await taste.workspace(owner))["revision"] == 0


async def test_history_job_survives_redelivery_and_serializes_real_source_dates(
    client, pool, monkeypatch
):
    from datetime import UTC, datetime

    owner, _ = await user(client, pool)
    row = await taste.workspace(owner, create=True)
    found = {"results": [{"id": str(uuid4()), "kind": "local", "started_at": datetime.now(UTC)}]}
    search = AsyncMock(return_value=found)
    monkeypatch.setattr(taste.history, "search", search)
    job = await pool.fetchval(
        "INSERT INTO taste_jobs(workspace_id,operation,status,input) VALUES($1,'discover','running',$2) RETURNING id",
        row["id"],
        {"query": "website"},
    )
    await taste.run_job(job)
    await taste.run_job(job)
    saved = await pool.fetchrow("SELECT status,result FROM taste_jobs WHERE id=$1", job)
    assert saved["status"] == "succeeded"
    assert isinstance(saved["result"]["results"][0]["started_at"], str)
    assert search.await_count == 1
    assert len((await taste.workspace(owner))["config"]["sources"]) == 1


async def test_build_connects_reviewed_evidence_to_a_new_generation_experiment_without_resetting_budget(
    client, pool, tmp_path, monkeypatch
):
    from scripts.website_taste import probe_pipeline, protocol
    from scripts.website_taste.corpus import digest

    owner, _ = await user(client, pool)
    row = await taste.workspace(owner, create=True)
    examples = []
    for partition in ("train", "dev", "test"):
        for label in ("liked", "disliked"):
            image = tmp_path / f"{partition}-{label}.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + (partition + label).encode())
            packet = evidence.packet(
                "Build a website", {"steps": [], "coverage": {"complete": False}}, image
            )
            packet["supervision"] = {
                "partition": partition,
                "group": partition,
                "label": label,
                "human_reviewed": True,
                "quote": "Explicit choice",
                "provenance": {"reference_image": False},
            }
            examples.append(packet)
    dataset = {
        "examples": examples,
        "heldout_status": "previously_inspected_test",
        "label_policy": "human_reviewed",
    }
    dataset["sha256"] = digest(json.dumps(dataset, sort_keys=True))
    taste.write(tmp_path / "evidence.json", dataset)
    row["config"] = {"probe": str(tmp_path), "budget": str(tmp_path)}
    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path / "work"))
    calls = []
    monkeypatch.setattr(taste, "refresh_saved_scores", lambda *args: None)

    def extract(output, rows, *, budget_output):
        assert budget_output == tmp_path
        calls.append("remote-extract")

    def fit(output, *, budget_output):
        assert budget_output == tmp_path
        assert all(
            e["supervision"]["human_reviewed"]
            for e in taste.read(output / "evidence.json")["examples"]
        )
        calls.append("remote-fit")

    monkeypatch.setattr(probe_pipeline, "extract_features", extract)
    monkeypatch.setattr(probe_pipeline, "fit_probe", fit)
    result = taste.execute(row, "build")
    frozen = protocol.load(__import__("pathlib").Path(result["experiment"]))
    assert (
        frozen["sha256"]
        == taste.read(__import__("pathlib").Path(result["probe"]) / "evidence.json")[
            "source_experiment"
        ]
    )
    assert calls == ["remote-extract", "remote-fit"]
    assert result["budget"] == str(tmp_path)
    assert {e["partition"] for e in frozen["examples"]} == {"train", "dev", "test"}


def test_rebuilt_probe_rechecks_human_counterexamples_without_promoting_agent_opinions(
    tmp_path, monkeypatch
):
    from scripts.website_taste import probe_pipeline

    old, new, experiment = tmp_path / "old", tmp_path / "new", tmp_path / "experiment"
    old.mkdir()
    new.mkdir()
    experiment.mkdir()
    identity, packet = "a" * 64, "b" * 64
    row = {"config": {"experiment": str(experiment)}}
    taste.write(old / "probe-audit.json", {"human_failures": [identity]})
    taste.write(
        old / "probe-predictions" / f"{identity}.json",
        {
            "trial_id": identity,
            "prediction": {"input_id": packet},
            "inputs": {"render": {"sha256": "pixels"}},
        },
    )
    taste.write(
        probe_pipeline.feature_path(old, packet),
        {"id": packet, "spec": SPEC, "pixel_sha256": "pixels", "activation": [1.0, 0.0]},
    )
    monkeypatch.setattr(
        probe_pipeline,
        "load_probe",
        lambda _: {
            "head": {"dimensions": 2, "weights": [-1.0, 0.0], "center": [0.0, 0.0], "bias": 0},
            "kind": "probe",
            "version": "new-version",
            "dataset": "dataset",
        },
    )
    taste.refresh_saved_scores(row, old, new)
    assert taste.read(new / "probe-audit.json")["human_failures"] == [identity]
    (experiment / "human-feedback.jsonl").write_text(
        json.dumps({"trial_id": identity, "label": "disliked"}) + "\n"
    )
    taste.refresh_saved_scores(row, old, new)
    assert taste.read(new / "probe-audit.json")["human_failures"] == []
    assert (
        taste.read(new / "probe-predictions" / f"{identity}.json")["prediction"]["reward"][
            "version"
        ]
        == "new-version"
    )


async def test_website_preference_setup_is_part_of_existing_eval_wizard(
    client, pool, tmp_path, monkeypatch
):
    from backend.services.intuition import wizard

    owner, headers = await user(client, pool)
    model = await __import__(
        "backend.services.intuition.service", fromlist=["create_model"]
    ).create_model(
        owner,
        name="Website design",
        output_type="choice",
        description="My UI preferences",
        labels=[
            {"id": "liked", "description": "keep"},
            {"id": "disliked", "description": "change"},
        ],
        rubric=[],
    )
    session = await wizard.create_session(owner, model["model"]["id"])
    row = await taste.workspace(owner, create=True)
    bundle(tmp_path)
    await pool.execute(
        "UPDATE taste_workspaces SET config=$2 WHERE id=$1", row["id"], {"probe": str(tmp_path)}
    )
    first = await client.post("/api/v1/taste/resume-wizard", headers=headers)
    second = await client.post("/api/v1/taste/resume-wizard", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["session_id"] == second.json()["session_id"] == session["id"]
    current = await wizard.get_session(owner, UUID(session["id"]))
    result, card = await wizard.run_tool(
        owner, current, "website_eval", {"operation": "prepare"}, lambda *args: None
    )
    assert (
        result["existing_examples"] == 1
        and card["kind"] == "website_eval"
        and card["props"]["section"] == "preferences"
    )
    state = await wizard.status(owner, current["model_id"])
    assert state["website_eval"]["grader"]["parameters"] == 3
    assert "search or import" in state["note"]
    result, card = await wizard.run_tool(
        owner, current, "website_eval", {"operation": "results"}, lambda *args: None
    )
    assert card["props"]["section"] == "results"
    with pytest.raises(taste.Conflict):
        await wizard.run_tool(
            owner, current, "website_eval", {"operation": "publish"}, lambda *args: None
        )
