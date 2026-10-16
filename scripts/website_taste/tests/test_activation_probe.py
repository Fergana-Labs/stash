import copy
import json

import pytest

from scripts.website_taste import activation_head, evidence, probe_pipeline
from scripts.website_taste.activation_spec import SPEC, model_text
from scripts.website_taste.activation_worker import extract, fit_probe
from scripts.website_taste.corpus import digest
from scripts.website_taste.runtime import Runner


def write_events(path, texts):
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": role,
                        "content": [{"type": "input_text", "text": text}],
                    },
                }
            )
            for role, text in texts
        )
    )


def test_evidence_stops_before_target_feedback_and_never_reads_future(tmp_path):
    trace = tmp_path / "trace.jsonl"
    write_events(
        trace,
        [
            ("system", "PRIVATE POLICY"),
            ("user", "Build a website"),
            ("assistant", "Made compact rows"),
            ("user", "TARGET CRITICISM"),
            ("assistant", "FUTURE REPAIR"),
        ],
    )
    result = evidence.history_trace(trace, 4, target_quote="TARGET CRITICISM")
    assert [s["text"] for s in result["steps"]] == ["Build a website", "Made compact rows"]
    assert result["coverage"]["complete"] and result["coverage"]["future_steps_excluded"]
    image = tmp_path / "image.png"
    image.write_bytes(b"pixels")
    value = evidence.packet("Build a website", result, image)
    value["supervision"] = {
        "label": "disliked",
        "quote": "TARGET CRITICISM",
        "judge": "AGENT OPINION",
    }
    payload = evidence.model_payload(value)
    assert all(
        s not in json.dumps(payload)
        for s in (
            "TARGET CRITICISM",
            "AGENT OPINION",
            "PRIVATE POLICY",
            "FUTURE REPAIR",
            str(tmp_path),
        )
    )
    assert "Made compact rows" in model_text(payload["input"])
    image.write_bytes(b"modified")
    with pytest.raises(ValueError, match="Screenshot changed"):
        evidence.model_payload(value)


def test_linear_probe_fits_training_only_and_is_not_an_agent_verdict():
    rows = [
        {"id": str(i), "activation": x, "label": label, "partition": part}
        for i, (x, label, part) in enumerate(
            [
                ([1.0, 0.0], "liked", "train"),
                ([0.9, 0.1], "liked", "train"),
                ([-1.0, 0.0], "disliked", "train"),
                ([-0.9, -0.1], "disliked", "train"),
                ([0.0, 1.0], "liked", "dev"),
                ([0.0, -1.0], "disliked", "test"),
            ]
        )
    ]
    head = activation_head.fit(rows)
    altered = copy.deepcopy(rows)
    altered[-1].update(label="liked", activation=[9999.0, -9999.0])
    altered[-2].update(label="disliked", activation=[-9999.0, 9999.0])
    assert activation_head.fit(altered) == head
    assert activation_head.predict(head, [1.0, 0.0])["label"] == "liked"
    assert activation_head.predict(head, [-1.0, 0.0])["label"] == "disliked"
    assert not activation_head.predict(head, [1.0, 0.0])["calibrated"]
    with pytest.raises(ValueError, match="shape"):
        activation_head.predict(head, [float("nan"), 0.0])


def test_high_teacher_agreement_cannot_release_an_unreviewed_probe():
    scores = {
        "n": 10,
        "accuracy": 1,
        "per_class": {label: {"n": 5, "recall": 1} for label in ("liked", "disliked")},
    }
    dataset = {
        "heldout_status": "reused teacher checks",
        "examples": [{"supervision": {"human_reviewed": False}}],
    }
    gate = activation_head.release_gate(dataset, {"dev": scores, "test": scores})
    assert not gate["passed"]
    assert gate["checks"]["test_agreement"]
    assert not gate["checks"]["source_grounded_labels"]
    assert not gate["checks"]["fresh_human_holdout"]


def test_cloud_only_guard_precedes_model_loading():
    with pytest.raises(RuntimeError, match="never be loaded"):
        extract([], SPEC)
    with pytest.raises(RuntimeError, match="never be loaded"):
        fit_probe([])


def test_evidence_redacts_credentials_without_treating_text_as_commands():
    text = 'export STASH_API_KEY=do-not-send; {"api_key": "also-private", "password": "sensitive"}; Bearer secret-token'
    result = evidence.clean(text)
    assert all(
        s not in result for s in ("do-not-send", "also-private", "sensitive", "secret-token")
    )
    assert "[redacted]" in result


def test_posttraining_identity_pins_the_reward_and_pair_contents():
    from scripts.website_taste.experiment import training_identity

    config = {"sha256": "frozen", "seed": 1, "dpo_steps": 40, "dpo_beta": 0.1}
    reward = {"version": "one"}
    pairs = [{"reward": reward, "partition": "train", "chosen": "A", "rejected": "B"}]
    first, identity = training_identity(config, pairs, reward)
    changed = [{**pairs[0], "chosen": "Different output"}]
    assert training_identity(config, changed, reward)[1] != identity
    with pytest.raises(ValueError, match="different reward"):
        training_identity(config, pairs, {"version": "two"})
    assert first["reward"] == reward and first["pairs_sha256"]


def test_extraction_cache_pins_pixels_and_representation_and_counts_failures(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"pixels")
    value = evidence.packet("Brief", {"steps": [], "coverage": {"complete": False}}, image)
    calls = []

    def fake(payloads, spec):
        calls.append(payloads)
        assert "supervision" not in json.dumps(payloads)
        return {
            "spec": spec,
            "backbone_frozen": True,
            "gpu_seconds": 0.1,
            "features": [
                {
                    "id": p["id"],
                    "spec": spec,
                    "activation": [1.0, 2.0],
                    "dimensions": 2,
                    "generated_tokens": 0,
                    "trainable_backbone_parameters": 0,
                    "pixel_sha256": p["input"]["render"]["sha256"],
                }
                for p in payloads
            ],
        }

    first = probe_pipeline.extract_features(tmp_path, [value], remote=fake)
    assert probe_pipeline.extract_features(tmp_path, [value], remote=fake) == first
    assert len(calls) == 1
    image.write_bytes(b"changed pixels")
    with pytest.raises(ValueError, match="Screenshot changed"):
        probe_pipeline.extract_features(tmp_path, [value], remote=fake)
    probe_pipeline.reserve(tmp_path, "extract")
    probe_pipeline.reserve(tmp_path, "extract")
    with pytest.raises(ValueError, match="budget exhausted"):
        probe_pipeline.reserve(tmp_path, "extract")


def test_runner_passes_real_response_and_artifacts_to_activation_scorer(tmp_path):
    spec = {"id": "fake", "revision": "frozen"}
    observed = []

    class Scorer:
        identity = {"kind": "activation-probe", "version": "one"}

        def score_run(self, task, messages, generation, html, png):
            assert html.read_text() == generation["text"] and png.read_bytes() == b"pixels"
            observed.append((task, messages, generation))
            return {"score": 0.6, "calibrated": False}

    def render(html, png):
        png.write_bytes(b"pixels")

    runner = Runner(
        tmp_path,
        {"model": spec, "sha256": "exp", "seed": 1},
        lambda *a, **k: {"text": "<html>Actual website</html>", "model": spec},
        Scorer(),
        render_fn=render,
    )
    result = runner.run(
        {"id": "task", "brief": "Actual request", "partition": "train"}, "Candidate skill", "skill"
    )
    assert result["score"] == 0.6 and observed[0][1][-1]["content"] == "Actual request"
    assert result["reward"]["version"] == "one"
    with pytest.raises(ValueError, match="Reward changed"):

        class Other(Scorer):
            identity = {"kind": "activation-probe", "version": "two"}

        Runner(tmp_path, {}, None, Other())


def test_dataset_rejects_related_evidence_across_splits(tmp_path):
    data = {
        "examples": [
            {
                "input": {"render": {"sha256": "same-pixels"}},
                "supervision": {"group": part, "partition": part},
            }
            for part in ("train", "test")
        ]
    }
    data["sha256"] = digest(json.dumps(data, sort_keys=True))
    (tmp_path / "evidence.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="crosses"):
        probe_pipeline.dataset_at(tmp_path)


def test_agent_disagreement_flags_review_but_human_counterexample_blocks(tmp_path, monkeypatch):
    record = {
        "kind": "activation-probe",
        "version": "frozen",
        "dataset": "data",
        "release_gate": {"passed": True},
    }
    monkeypatch.setattr(probe_pipeline, "load_probe", lambda output: record)
    audit = tmp_path / "probe-audit.json"
    audit.write_text(
        json.dumps({"version": "frozen", "agent_disagreements": ["one"], "human_failures": []})
    )
    assert probe_pipeline.ProbeScorer(tmp_path).identity["version"] == "frozen"
    audit.write_text(json.dumps({"version": "frozen", "human_failures": ["one"]}))
    with pytest.raises(ValueError, match="confirmed human counterexample"):
        probe_pipeline.ProbeScorer(tmp_path)
    # The exploratory inspection path is available without enabling optimization.
    assert probe_pipeline.ProbeScorer(tmp_path, exploratory=True)


def test_fresh_holdout_attestation_rejects_already_used_source(tmp_path):
    from scripts.website_taste import protocol

    source, history, output = tmp_path / "source", tmp_path / "history", tmp_path / "output"
    source.mkdir()
    history.mkdir()
    (history / "candidates.jsonl").write_text("")
    (source / "SKILL.md").write_text("Baseline skill")
    rows = []
    for part in ("train", "dev", "test"):
        for label in ("liked", "disliked"):
            image = source / (part + label + ".png")
            image.write_bytes((part + label).encode())
            rows.append(
                {
                    "id": part + label,
                    "partition": part,
                    "group": part,
                    "sha256": digest(image.read_bytes()),
                    "file": str(image),
                    "label": label,
                    "human_reviewed": True,
                    "needs_review": False,
                }
            )
    protocol.seal(source, rows, protocol.tasks(), {"id": "fake", "revision": "pinned"})
    assert (
        evidence.prepare(source, history, output, fresh_human_holdout=True)["heldout_status"]
        == "untouched_human_test"
    )
    (source / "classifier-training.json").write_text("{}")
    with pytest.raises(ValueError, match="already used"):
        evidence.prepare(source, history, tmp_path / "second", fresh_human_holdout=True)
