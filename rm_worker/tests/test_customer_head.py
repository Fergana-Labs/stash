import copy
import json
import sys
from types import SimpleNamespace

import pytest

from rm_worker import score_run
from rm_worker.customer_head import compare_features, fit_customer_head, score_features

PIN = {"feature_version": "1" * 64, "manifest_digest": "2" * 64}


def test_zero_labels_preserves_global_head_exactly():
    head = fit_customer_head([], [1.25, -0.5], **PIN)
    assert head["residual_weights"] == [0, 0]
    assert score_features([2, 4], head, **PIN) == 0.5
    assert not compare_features([2, 4], [0, 0], head, **PIN)["calibrated"]


def test_customer_labels_fit_only_a_regularized_residual():
    pairs = [{"chosen": [-1, 0], "rejected": [1, 0], **PIN}]
    original = copy.deepcopy(pairs)
    head = fit_customer_head(pairs, [1, 0], l2=0.1, **PIN)
    assert head["global_weights"] == [1, 0]
    assert head["residual_weights"][0] < -1
    assert head["residual_weights"][1] == 0
    assert compare_features([-1, 0], [1, 0], head, **PIN)["p_a_wins"] > 0.5
    assert pairs == original


@pytest.mark.parametrize("bad", [[float("nan")], [True], [], [1, 2], [float("inf")]])
def test_bad_features_fail_closed(bad):
    head = fit_customer_head([], [1], **PIN)
    with pytest.raises(ValueError):
        score_features(bad, head, **PIN)


def test_every_pair_and_prediction_requires_exact_feature_identity():
    pair = {"chosen": [1], "rejected": [-1], **PIN}
    pair["manifest_digest"] = "3" * 64
    with pytest.raises(ValueError, match="another shared basis"):
        fit_customer_head([pair], [1], **PIN)
    head = fit_customer_head([], [1], **PIN)
    with pytest.raises(ValueError, match="another shared basis"):
        score_features([1], head, feature_version="4" * 64, manifest_digest=PIN["manifest_digest"])


def test_stronger_regularization_stays_closer_to_global_prior():
    pairs = [{"chosen": [-1], "rejected": [1], **PIN}]
    weak = fit_customer_head(pairs, [1], l2=0.1, **PIN)
    strong = fit_customer_head(pairs, [1], l2=10, **PIN)
    assert abs(strong["residual_weights"][0]) < abs(weak["residual_weights"][0])


def test_saved_worker_forwards_pinned_customer_head_and_records_actual_manifest(
    tmp_path, monkeypatch
):
    head = fit_customer_head([], [1], **PIN)
    head.update(head_id="customer", head_version=3)
    manifest = {"evaluator_kind": "shared_basis_v1", **PIN}
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "action_reward_stats.json").write_text('{"mean":0,"std":1}')
    received = []

    class Model:
        def __init__(self, path):
            self.basis = SimpleNamespace(manifest=manifest)

        def score(self, texts, *, on_progress=None, head=None):
            received.append(head)
            return [2.0] * len(texts)

    monkeypatch.setitem(sys.modules, "rm_worker.scoring", SimpleNamespace(RewardModel=Model))
    monkeypatch.setattr(score_run, "download_model", lambda key, path: checkpoint)
    (tmp_path / "job.json").write_text(
        json.dumps({"reward_model_key": "private", "customer_head": head})
    )
    (tmp_path / "action_score_items.jsonl").write_text(
        json.dumps({"trace_id": "trace", "step_id": "action", "text": "task + action"}) + "\n"
    )
    score_run.run(tmp_path)
    assert received == [head]
    result = json.loads((tmp_path / "result.json").read_text())["customer_provenance"]
    assert result["feature_version"] == manifest["feature_version"]
    assert result["customer_head_version"] == 3
    assert result["score_scale"] == "global_training_reward_normalization"
    assert len(result["head_snapshot_digest"]) == 64


def test_legacy_saved_worker_refuses_customer_head(tmp_path, monkeypatch):
    class Model:
        basis = None

        def __init__(self, path):
            pass

    monkeypatch.setitem(sys.modules, "rm_worker.scoring", SimpleNamespace(RewardModel=Model))
    monkeypatch.setattr(score_run, "download_model", lambda key, path: tmp_path)
    (tmp_path / "job.json").write_text(
        json.dumps({"reward_model_key": "old", "customer_head": fit_customer_head([], [1], **PIN)})
    )
    with pytest.raises(ValueError, match="require a shared"):
        score_run.run(tmp_path)
