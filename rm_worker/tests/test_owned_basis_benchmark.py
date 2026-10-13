"""Contract tests using a fake tokenizer/features, never a downloaded model."""

import hashlib
import json

import pytest

from backend.scripts.prepare_owned_basis_benchmark import (
    complete,
    oracle_valid,
    owned_case,
    prepare,
)
from rm_worker.basis_validation import canonical_digest


class TinyTemplate:
    def apply_chat_template(self, messages, **kwargs):
        return json.dumps(messages, sort_keys=True)


def prepared(tmp_path, monkeypatch):
    transformers = pytest.importorskip("transformers")
    monkeypatch.setattr(
        transformers.AutoTokenizer, "from_pretrained", lambda *args, **kwargs: TinyTemplate()
    )
    source = tmp_path / "source"
    source.mkdir()
    manifest = {
        "basis_dimension": 4,
        "global_head": {"weights": [1, 0, 0, 0]},
        "feature_version": canonical_digest("owned-feature-fixture"),
        "manifest_digest": canonical_digest("owned-manifest-fixture"),
        "training_lineage": {
            "customer_ids": [],
            "workflow_ids": ["source-general"],
            "profile_ids": ["criterion"],
            "task_groups": ["source-group"],
            "example_ids": ["source-example"],
        },
    }
    (source / "job.json").write_text(
        json.dumps(
            {
                "base_model": "fake-tokenizer-only",
                "base_model_revision": "fixture",
                "artifact_key": "fake-checkpoint",
            }
        )
    )
    (source / "result.json").write_text(json.dumps({"metrics": {"basis_manifest": manifest}}))
    output = tmp_path / "owned"
    summary = prepare(source, output)
    return output, summary, manifest


def write_fake_features(output, manifest):
    rows = []
    for line in (output / "feature_items.jsonl").read_text().splitlines():
        item = json.loads(line)
        # Every mocked score is zero. This tests reporting contracts, not quality.
        rows.append(
            {
                "id": item["id"],
                "input_digest": hashlib.sha256(item["text"].encode()).hexdigest(),
                "features": [0, 0, 0, 0],
                "feature_version": manifest["feature_version"],
                "manifest_digest": manifest["manifest_digest"],
            }
        )
    (output / "features.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_owned_preparation_freezes_distinct_oracle_cohorts_and_420_inputs(tmp_path, monkeypatch):
    output, summary, _ = prepared(tmp_path, monkeypatch)
    assert summary["feature_inputs"] == 420
    dataset = json.loads((output / "pairs.json").read_text())
    assert len(dataset["comparisons"]) == 160
    support = {row["task_group"] for row in dataset["comparisons"] if row["partition"] == "support"}
    test = {row["task_group"] for row in dataset["comparisons"] if row["partition"] == "test"}
    cases = json.loads((output / "attack_cases.json").read_text())
    assert not support & test
    assert not {case["task_group"] for case in cases} & (support | test)
    for row in dataset["comparisons"]:
        assert oracle_valid(row["task"], row[row["label"]]["artifact"])
        assert row["label_provenance"]["synthetic"]
    for case in cases:
        assert oracle_valid(case["facts"], case["valid_baseline_artifact"])
        assert all(
            not oracle_valid(case["facts"], candidate["artifact"])
            for candidate in case["candidates"]
        )


def test_owned_completion_preserves_synthetic_and_insufficient_budget_status(tmp_path, monkeypatch):
    output, _, manifest = prepared(tmp_path, monkeypatch)
    write_fake_features(output, manifest)
    result = complete(output)
    assert result["scope"] == "synthetic_regression_only"
    report = json.loads((output / "validation_report.json").read_text())
    assert report["product_gate"]["status"] == "not_assessed"
    for target in report["learning_curves"]["targets"]:
        assert target["budgets"][-2]["status"] == "insufficient_support"
        assert target["budgets"][-1]["status"] == "insufficient_support"
    assert report["adaptive_attacks"][0]["campaign_count"] == 20
    assert all(attack["one_sided_exact_upper"] is None for attack in report["adaptive_attacks"])
    assert report["claims"]["actual_agent_improvement"]["status"] == "unsupported"


def test_owned_completion_rejects_features_for_different_input(tmp_path, monkeypatch):
    output, _, manifest = prepared(tmp_path, monkeypatch)
    write_fake_features(output, manifest)
    rows = [json.loads(line) for line in (output / "features.jsonl").read_text().splitlines()]
    rows[0]["input_digest"] = canonical_digest("different input")
    (output / "features.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="serialized input"):
        complete(output)


def test_arithmetic_oracle_rejects_boolean_answer():
    task, _, _ = owned_case("arithmetic", 0)
    assert not oracle_valid(task, {"answer": True})
