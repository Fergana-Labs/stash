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


@pytest.mark.parametrize("automatic", [False, True])
async def test_build_connects_grounded_evidence_without_manual_review_or_resetting_budget(
    client, pool, tmp_path, monkeypatch, automatic
):
    from scripts.website_taste import probe_pipeline, protocol
    from scripts.website_taste.corpus import digest

    owner, _ = await user(client, pool)
    row = await taste.workspace(owner, create=True)
    examples = []
    for partition in ("train", "dev", "test"):
        for index, label in enumerate(
            ("liked", "disliked", "liked", "disliked")
            if partition == "train"
            else ("liked", "disliked")
        ):
            image = tmp_path / f"{partition}-{label}-{index}.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + (partition + label + str(index)).encode())
            packet = evidence.packet(
                "Build a website", {"steps": [], "coverage": {"complete": False}}, image
            )
            packet["supervision"] = {
                "partition": partition,
                "group": partition,
                "label": label,
                "human_reviewed": not automatic,
                "quote": "Explicit choice",
                "provenance": {"reference_image": False},
            }
            if automatic:
                packet["supervision"].update(
                    label_source="explicit_feedback_auto",
                    scope="overall",
                    feedback_evidence={
                        "schema": 1,
                        "render_inspected": True,
                        "image_role": "output",
                        "explicit": True,
                        "target": "single",
                        "image_count": 1,
                        "image_index": 1,
                        "session_id": partition,
                        "line": 2,
                        "sha256": packet["input"]["render"]["sha256"],
                        "feedback": "Explicit choice",
                        "quote": "Explicit choice",
                        "label": label,
                        "scope": "overall",
                    },
                )
            examples.append(packet)
    # Neither uncertainty nor a teacher's opinion holds up the clear examples.
    import copy

    for source in ("teacher_inferred", "explicit_feedback_auto"):
        value = copy.deepcopy(examples[0])
        value["id"] = source
        value["supervision"].update(human_reviewed=False, label_source=source)
        value["supervision"].pop("feedback_evidence", None)
        examples.append(value)
    dataset = {
        "examples": examples,
        "heldout_status": "previously_inspected_test",
        "label_policy": "human_reviewed",
    }
    dataset["sha256"] = digest(json.dumps(dataset, sort_keys=True))
    taste.write(tmp_path / "evidence.json", dataset)
    row["config"] = {"probe": str(tmp_path), "budget": str(tmp_path)}
    await pool.execute(
        "UPDATE taste_workspaces SET config=$2 WHERE id=$1", row["id"], row["config"]
    )
    if automatic:
        state = await taste.detail(owner)
        assert state["labels"]["usable"] == 8 and state["reviewed"] == 0
        assert state["labels"]["needs_clarification"] == 1
        assert state["labels"]["model_guesses"] == 1
        assert not state["labels"]["build_gaps"]
        monkeypatch.setenv("TASTE_CLOUD_ENABLED", "1")
        dispatch = []
        monkeypatch.setattr(taste_tasks.run, "delay", lambda job: dispatch.append(job))
        queued = await taste.enqueue(owner, "build", {})
        assert dispatch == [str(queued["job_id"])]
    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path / "work"))
    calls = []
    monkeypatch.setattr(taste, "refresh_saved_scores", lambda *args: None)

    def extract(output, rows, *, budget_output):
        assert budget_output == tmp_path
        calls.append("remote-extract")

    def fit(output, *, budget_output):
        assert budget_output == tmp_path
        fitted = taste.read(output / "evidence.json")["examples"]
        assert len(fitted) == 8
        assert all(e["supervision"]["human_reviewed"] is not automatic for e in fitted)
        assert all("feedback_evidence" not in e["input"] for e in fitted)
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
    assert frozen["label_policy"] == "source_grounded"
    assert all(e["human_reviewed"] is not automatic for e in frozen["examples"])


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
        and card["props"]["section"] == "progress"
    )
    state = await wizard.status(owner, current["model_id"])
    assert state["website_eval"]["endpoint"]["ready"]
    assert "upload card" in state["note"]
    result, card = await wizard.run_tool(
        owner, current, "website_eval", {"operation": "results"}, lambda *args: None
    )
    assert card["props"]["section"] == "connect"
    result, card = await wizard.run_tool(
        owner, current, "website_eval", {"operation": "finish"}, lambda *args: None
    )
    assert result["published"] and result["endpoint"]["ready"]
    assert card["props"]["section"] == "connect"
    assert (await taste.detail(owner))["grader"]["released"] is False


@pytest.mark.parametrize("bad_field", ["id", "target", "quote"])
async def test_feedback_extraction_repairs_source_ids_and_reuses_receipts(
    tmp_path, monkeypatch, bad_field
):
    from types import SimpleNamespace

    from scripts.website_taste.preferences import source_label

    image = tmp_path / "image.png"
    image.write_bytes(b"test-pixels")
    import hashlib

    pixel_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "scripts.website_taste.autolabel.pixels",
        lambda _: {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "AA=="},
        },
    )
    source = {
        "id": "long-exact-session-id:3:1",
        "session_id": "session",
        "line": 3,
        "sha256": pixel_hash,
        "file": str(image),
        "image_index": 1,
        "image_count": 2,
        "feedback": "This website looks terrible",
    }
    proposal = {
        "id": "e1",
        "label": "disliked",
        "quote": source["feedback"],
        "scope": "overall",
        "image_role": "output",
        "explicit": True,
        "target": "explicit",
        "reason": "Direct visual criticism",
    }

    def reply(value):
        return SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(value))]
        )

    create = AsyncMock(
        side_effect=[
            reply(
                {
                    "proposals": [
                        {
                            **proposal,
                            bad_field: {
                                "id": "made-up",
                                "target": "single",
                                "quote": "Paraphrased criticism",
                            }[bad_field],
                        }
                    ]
                }
            ),
            reply({"proposals": [proposal]}),
        ]
    )
    monkeypatch.setattr(
        "anthropic.AsyncAnthropic",
        lambda **kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    first = await taste.extract_feedback([source], tmp_path)
    assert first[0]["id"] == source["id"]
    assert source_label(
        {**first[0], "label_source": "explicit_feedback_auto"}, pixel_sha=pixel_hash
    )
    assert create.await_count == 2
    again = await taste.extract_feedback([source], tmp_path)
    assert again == first and create.await_count == 2


async def test_demo_reset_starts_empty_preserves_archives_and_shared_budget(
    client, pool, tmp_path, monkeypatch
):
    from pathlib import Path

    from backend.services.intuition import wizard

    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path / "runs"))
    owner, headers = await user(client, pool)
    binding = await taste.bind_wizard(owner)
    old_id = UUID(binding["session_id"])
    item, probe = bundle(tmp_path)
    ledger = tmp_path / "probe-cloud-ledger.jsonl"
    ledger.write_text('{"kind":"extract","reserved_usd":0.93}\n')
    await pool.execute(
        "UPDATE taste_workspaces SET config=config || $2::jsonb,reviews=$3,revision=2,fitted_revision=2 WHERE owner_user_id=$1",
        owner,
        {"probe": str(tmp_path), "budget": str(tmp_path), "published": True},
        {item["id"]: {"label": "disliked", "note": "Observed"}},
    )
    row = await taste.workspace(owner)
    old_root = taste.work_root(row)
    await pool.execute(
        "INSERT INTO taste_jobs(workspace_id,operation,status) VALUES($1,'build','succeeded')",
        row["id"],
    )
    await pool.execute(
        "INSERT INTO taste_predictions(workspace_id,version,input,output) VALUES($1,$2,'{}','{}')",
        row["id"],
        probe["version"],
    )
    await wizard.save_draft(owner, old_id, "Keep this unsent note")
    stale_session = await wizard.get_session(owner, old_id)
    response = await client.post(
        "/api/v1/taste/reset", headers=headers, json={"session_id": str(old_id)}
    )
    assert response.status_code == 200, response.text
    fresh_id = UUID(response.json()["session_id"])
    assert fresh_id != old_id
    state = await taste.detail(owner)
    assert state["examples"] == state["jobs"] == state["predictions"] == state["trials"] == []
    assert state["grader"]["version"] is None and not state["published"]
    assert state["model_id"] is None and state["labels"]["usable"] == 0
    fresh = await wizard.get_session(owner, fresh_id)
    assert (
        fresh["model_id"] is None
        and fresh["transcript"] == []
        and fresh["brief"] == {}
        and fresh["draft_input"] == ""
    )
    await wizard._save(stale_session)  # A late response cannot undo the archive.
    with pytest.raises(taste.Conflict, match="reset"):
        await taste.bind_wizard(owner, stale_session)
    archived = await wizard.get_session(owner, old_id)
    assert (
        archived["reset_to"] == str(fresh_id) and archived["draft_input"] == "Keep this unsent note"
    )
    assert str(old_id) not in {s["id"] for s in await wizard.list_sessions(owner)}
    blocked = await client.post(
        f"/api/v1/model-wizard/sessions/{old_id}/messages",
        headers=headers,
        json={"text": "Continue"},
    )
    assert blocked.status_code == 409
    after = await taste.workspace(owner)
    assert taste.location(after, "budget") == tmp_path
    assert ledger.read_text() == '{"kind":"extract","reserved_usd":0.93}\n'
    assert taste.work_root(after) != old_root
    snapshot = taste.read(Path(after["config"]["archives"][-1]))
    assert (
        snapshot["config"]["probe"] == str(tmp_path)
        and snapshot["reviews"][item["id"]]["label"] == "disliked"
    )
    assert taste.read(tmp_path / "activation-probe.json")["version"] == probe["version"]
    retry = await client.post(
        "/api/v1/taste/reset", headers=headers, json={"session_id": str(old_id)}
    )
    assert retry.json()["session_id"] == str(fresh_id)
    resumed = await taste.bind_wizard(owner)
    assert resumed["session_id"] == str(fresh_id) and resumed["model_id"] != binding["model_id"]
    assert (await taste.detail(owner))["examples"] == []


async def test_demo_reset_is_owner_scoped_and_waits_for_active_jobs(
    client, pool, tmp_path, monkeypatch
):
    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path))
    owner, headers = await user(client, pool)
    binding = await taste.bind_wizard(owner)
    row = await taste.workspace(owner)
    _, outsider = await user(client, pool)
    request = {"session_id": binding["session_id"]}
    assert (
        await client.post("/api/v1/taste/reset", headers=outsider, json=request)
    ).status_code == 404
    await pool.execute(
        "INSERT INTO taste_jobs(workspace_id,operation) VALUES($1,'discover')", row["id"]
    )
    response = await client.post("/api/v1/taste/reset", headers=headers, json=request)
    assert response.status_code == 409 and "still working" in response.text
    assert (await taste.workspace(owner))["config"] == row["config"]


async def test_initial_endpoint_build_needs_no_validation_split(
    client, pool, tmp_path, monkeypatch
):
    from scripts.website_taste import probe_pipeline, protocol

    owner, _ = await user(client, pool)
    row = await taste.workspace(owner, create=True)
    items = []
    for i, label in enumerate(("liked", "disliked", "liked", "disliked")):
        path = tmp_path / f"{i}.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + str(i).encode())
        packet = evidence.packet(
            "Build a website", {"steps": [], "coverage": {"complete": False}}, path
        )
        packet["supervision"] = {
            "label": label,
            "human_reviewed": True,
            "partition": "train",
            "group": "one-source",
            "quote": "Explicit feedback",
            "provenance": {},
        }
        items.append(packet)
    taste.write(
        tmp_path / "evidence.json", {"examples": items, "heldout_status": "not_yet_reserved"}
    )
    row["config"] = {"dataset": str(tmp_path), "budget": str(tmp_path)}
    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path / "work"))
    monkeypatch.setattr(probe_pipeline, "extract_features", lambda *a, **kw: None)
    monkeypatch.setattr(probe_pipeline, "fit_probe", lambda *a, **kw: None)
    monkeypatch.setattr(taste, "refresh_saved_scores", lambda *a: None)
    assert not taste.label_summary(row)["build_gaps"]
    result = taste.execute(row, "build")
    from pathlib import Path

    frozen = protocol.load(Path(result["experiment"]))
    assert {e["partition"] for e in frozen["examples"]} == {"train"}
    assert frozen["require_holdout"] is False
    assert (
        taste.read(Path(result["dataset"]) / "evidence.json")["heldout_status"] == "not_available"
    )


async def test_uploaded_traces_feed_same_automatic_pipeline(client, pool, tmp_path, monkeypatch):
    from backend.services.intuition import wizard
    from scripts.website_taste.preferences import validate_proposals

    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("TASTE_CLOUD_ENABLED", "1")
    monkeypatch.setattr(taste_tasks.run, "delay", lambda *args: None)

    async def extract(batch, cache):
        return validate_proposals(
            [{**r, "render_inspected": True} for r in batch],
            {
                "proposals": [
                    {
                        "id": r["id"],
                        "label": "disliked",
                        "scope": "overall",
                        "quote": "This looks terrible",
                        "explicit": True,
                        "target": "single",
                        "image_role": "output",
                        "preference": "Improve visual craft",
                    }
                    for r in batch
                ]
            },
        )

    monkeypatch.setattr(taste, "extract_feedback", extract)
    owner, headers = await user(client, pool)
    session = await wizard.create_session(owner)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
    lines = [
        {"type": "response_item", "payload": {"type": "message", "role": role, "content": content}}
        for role, content in [
            ("developer", [{"type": "input_text", "text": "PRIVATE SYSTEM CONTENT"}]),
            ("user", [{"type": "input_text", "text": "Build a website"}]),
            ("assistant", [{"type": "output_text", "text": "Created the website"}]),
            (
                "user",
                [
                    {"type": "input_text", "text": "This looks terrible"},
                    {"type": "input_image", "image_url": "data:image/png;base64," + png},
                ],
            ),
        ]
    ]
    request = {
        "session_id": session["id"],
        "files": [{"name": "session.jsonl", "content": "\n".join(json.dumps(v) for v in lines)}],
    }
    response = await client.post("/api/v1/taste/traces", headers=headers, json=request)
    assert response.status_code == 200, response.text
    await taste.run_job(UUID(response.json()["job_id"]))
    row = await taste.workspace(owner)
    packet = taste.data(row)["examples"][0]
    assert packet["supervision"]["label"] == "disliked"
    assert "This looks terrible" not in json.dumps(packet["input"])
    assert "PRIVATE SYSTEM CONTENT" not in json.dumps(packet["input"])
    assert (await taste.detail(owner))["labels"]["usable"] == 1
    assert {
        t["name"]
        for t in await wizard.setup_tools(
            owner, await wizard.get_session(owner, UUID(session["id"]))
        )
    } == {"website_eval", "search_history", "read_history"}
    with pytest.raises(ValueError, match="private storage"):
        await taste.learn_uploaded_traces(row, ["/etc/passwd"])


async def test_collection_continues_to_endpoint_without_browser(
    client, pool, tmp_path, monkeypatch
):
    owner, _ = await user(client, pool)
    row = await taste.workspace(owner, create=True)
    monkeypatch.setenv("TASTE_CLOUD_ENABLED", "1")
    monkeypatch.setattr(taste_tasks.run, "delay", lambda *a: None)
    monkeypatch.setattr(taste, "extract_existing_labels", AsyncMock(return_value={"usable": 4}))
    monkeypatch.setattr(taste, "label_summary", lambda row: {"build_gaps": []})
    job = await taste.enqueue(owner, "extract_labels", {"automatic": True})
    await taste.run_job(job["job_id"])
    build = await pool.fetchrow(
        "SELECT * FROM taste_jobs WHERE workspace_id=$1 AND operation='build'", row["id"]
    )
    assert build and build["status"] == "queued" and build["input"]["automatic"]
    monkeypatch.setattr(taste, "execute", lambda *a: {"probe": str(tmp_path)})
    await taste.run_job(build["id"])
    fresh = await taste.workspace(owner)
    assert fresh["config"]["published"] is True
    assert fresh["fitted_revision"] == fresh["revision"]


async def test_failed_endpoint_fit_does_not_retry_paid_work(client, pool, monkeypatch):
    from backend.services.intuition import wizard

    owner, _ = await user(client, pool)
    session = await wizard.create_session(owner)
    await taste.bind_wizard(owner, session)
    row = await taste.workspace(owner)
    await pool.execute(
        "INSERT INTO taste_jobs(workspace_id,operation,status,progress) VALUES($1,'build','failed','Provider unavailable')",
        row["id"],
    )
    result, _ = await wizard.website_tool(owner, session, {"operation": "finish"}, lambda *a: None)
    assert result["status"] == "needs_attention"
    assert result["error"] == "Provider unavailable"
    assert (
        await pool.fetchval("SELECT count(*) FROM taste_jobs WHERE workspace_id=$1", row["id"]) == 1
    )


async def test_new_website_eval_asks_for_traces_before_searching(
    client, pool, tmp_path, monkeypatch
):
    from backend.services.intuition import wizard

    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("TASTE_CLOUD_ENABLED", "1")
    monkeypatch.setattr(taste_tasks.run, "delay", lambda *args: None)
    owner, headers = await user(client, pool)
    session = await wizard.create_session(owner)
    result, card = await wizard.run_tool(
        owner, session, "website_eval", {"operation": "prepare"}, lambda *args: None
    )
    assert card["props"]["section"] == "sources"
    assert result["existing_examples"] == 0 and "stop" in result["next"]
    session = await wizard.get_session(owner, UUID(session["id"]))
    result, card = await wizard.run_tool(
        owner, session, "website_eval", {"operation": "review"}, lambda *args: None
    )
    assert card["props"]["section"] == "preferences" and result["needs_your_call"] == 0
    result, card = await wizard.run_tool(
        owner, session, "website_eval", {"operation": "finish"}, lambda *args: None
    )
    assert result["status"] == "needs_information"
    assert card["props"]["section"] == "preferences"
    # A dropped history folder arrives as one upload of many session files.
    files = [{"name": f"s{i}.jsonl", "content": "{}"} for i in range(11)]
    response = await client.post(
        "/api/v1/taste/traces",
        headers=headers,
        json={"session_id": session["id"], "files": files},
    )
    assert response.status_code == 200, response.text
    assert response.json()["files_received"] == 11


def test_wizard_turn_ends_when_a_website_card_needs_the_user():
    from backend.services.intuition.wizard import _awaits_user

    card = lambda section: {"kind": "website_eval", "props": {"section": section}}  # noqa: E731
    assert _awaits_user(card("sources"), {})
    assert _awaits_user(card("preferences"), {"needs_your_call": 2})
    assert not _awaits_user(card("preferences"), {"needs_your_call": 0})
    assert not _awaits_user(card("progress"), {})
    assert not _awaits_user(None, {})


def test_website_design_requests_start_with_the_website_eval():
    from backend.services.intuition.wizard import _website_intent

    assert _website_intent("Learn my website design preferences from my past sessions")
    assert _website_intent("grade my landing page")
    assert not _website_intent("Grade my AI assistant's answers as good or bad")


async def test_example_sites_become_confirmed_training_examples(
    client, pool, tmp_path, monkeypatch
):
    from backend.services.intuition import wizard

    monkeypatch.setenv("TASTE_WORKSPACE_ROOT", str(tmp_path))
    owner, headers = await user(client, pool)
    session = await wizard.create_session(owner)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"liked").decode()
    other = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"disliked").decode()
    files = [
        {"name": "good.png", "label": "liked", "content": png},
        {"name": "bad.png", "label": "disliked", "content": other},
        {"name": "bad-again.png", "label": "disliked", "content": other},
    ]
    response = await client.post(
        "/api/v1/taste/examples",
        headers=headers,
        json={"session_id": session["id"], "files": files},
    )
    assert response.status_code == 200, response.text
    assert response.json()["added"] == {"liked": 1, "disliked": 1}
    examples = taste.effective_examples(await taste.workspace(owner))
    assert {(e["label"], e["usable"], e["reviewed"]) for e in examples} == {
        ("liked", True, True),
        ("disliked", True, True),
    }
    bad = {**files[0], "content": base64.b64encode(b"not an image").decode()}
    response = await client.post(
        "/api/v1/taste/examples",
        headers=headers,
        json={"session_id": session["id"], "files": [bad]},
    )
    assert response.status_code == 422
