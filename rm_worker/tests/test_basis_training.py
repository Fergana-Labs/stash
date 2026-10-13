"""Real artifact smoke tests using only a tiny local random encoder (<20K params)."""

import json

import numpy as np
import pytest


@pytest.fixture
def tiny_encoder(tmp_path):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    tokenizers = pytest.importorskip("tokenizers")
    torch.set_num_threads(1)
    torch.manual_seed(0)
    base = tmp_path / "tiny-base"
    vocabulary = {"[UNK]": 0, "[PAD]": 1, "good": 2, "bad": 3}
    vocabulary.update({f"task{i}": i + 4 for i in range(12)})
    implementation = tokenizers.Tokenizer(
        tokenizers.models.WordLevel(vocabulary, unk_token="[UNK]")
    )
    implementation.pre_tokenizer = tokenizers.pre_tokenizers.Whitespace()
    tokenizer = transformers.PreTrainedTokenizerFast(
        tokenizer_object=implementation,
        unk_token="[UNK]",
        pad_token="[PAD]",
        model_max_length=32,
    )
    tokenizer.save_pretrained(base)
    model = transformers.Qwen3ForSequenceClassification(
        transformers.Qwen3Config(
            vocab_size=len(vocabulary),
            hidden_size=8,
            num_hidden_layers=1,
            num_attention_heads=1,
            num_key_value_heads=1,
            intermediate_size=16,
            max_position_embeddings=128,
            num_labels=1,
            attention_dropout=0,
        )
    )
    assert sum(parameter.numel() for parameter in model.parameters()) < 20_000
    model.save_pretrained(base)
    return base


def make_job(tmp_path, base, monkeypatch):
    from rm_worker import basis_train

    pairs = [
        {
            "chosen": f"task{i} good",
            "rejected": f"task{i} bad",
            "example_id": f"pair{i}",
            "task_group": f"task{i}",
            "partition": "eval" if i >= 8 else "train",
            "profile_id": "customer-a" if i % 2 else "customer-b",
            "customer_id": "customer-a" if i % 2 else "customer-b",
            "domain": "coding" if i % 2 else "research",
            "granularity": "action",
            "action_type": "tool_call",
        }
        for i in range(10)
    ]
    job = {
        "kind": "basis_train",
        "fixed_split": True,
        "base_model": str(base),
        "base_model_license": "random_smoke_test",
        "epochs": 1,
        "artifact_key": "test/basis",
        "input_version": 1,
        "smoke_test": True,
        "basis_options": {"basis_dimension": 2, "fit_steps": 40, "max_length": 32},
    }
    (tmp_path / "job.json").write_text(json.dumps(job))
    basis_train.write_jsonl(tmp_path / "pairs.jsonl", pairs)
    basis_train.write_jsonl(
        tmp_path / "score_items.jsonl", [{"trace_id": "t1", "text": "task1 good"}]
    )
    basis_train.write_jsonl(
        tmp_path / "action_score_items.jsonl",
        [{"trace_id": "t1", "step_id": "a1", "text": "task1 good"}],
    )
    uploads = []
    monkeypatch.setattr(basis_train, "upload_model", lambda path, key: uploads.append((path, key)))
    return job, pairs, uploads


def test_shared_basis_export_reload_freezes_encoder_and_pins_head(
    tmp_path, monkeypatch, tiny_encoder
):
    torch = pytest.importorskip("torch")
    from rm_worker import basis, basis_train

    monkeypatch.setattr(basis, "pick_device", lambda: torch.device("cpu"))
    _, _, uploads = make_job(tmp_path, tiny_encoder, monkeypatch)
    result = basis_train.train(tmp_path)
    manifest = result["metrics"]["basis_manifest"]
    assert manifest["evaluator_kind"] == "shared_basis_v1"
    assert manifest["basis_dimension"] == 2
    assert manifest["manifest_digest"] == basis.manifest_digest(manifest)
    assert manifest["fitting_audit"]["optimized_encoder_parameters"] == 0
    assert manifest["fitting_audit"]["encoder_tensor_versions_unchanged"]
    assert manifest["fitting_audit"]["projection_changed"]
    assert manifest["fitting_audit"]["default_is_pretrained_anchor"]
    assert manifest["global_head"]["weights"] == [1.0, 0.0]
    assert manifest["basis_components"]["pretrained_anchor"]["enabled"]
    assert not manifest["basis_components"]["default_uses_learned_residual"]
    assert result["metrics"]["pretrained_eval_accuracy"] == result["metrics"]["eval_accuracy"]
    assert result["metrics"]["paired_wins_over_pretrained"] == 0
    assert result["metrics"]["paired_losses_to_pretrained"] == 0
    assert manifest["fitting_audit"]["source_profiles"] == 2
    assert manifest["training_lineage"]["customer_ids"] == ["customer-a", "customer-b"]
    assert manifest["training_lineage"]["workflow_ids"] == ["coding", "research"]
    assert "pair8" not in manifest["training_lineage"]["example_ids"]
    assert uploads == [(tmp_path / "model", "test/basis")]
    restored = basis.BasisRewardModel(tmp_path / "model")
    assert not any(parameter.requires_grad for parameter in restored.model.parameters())
    rows = basis_train.read_jsonl(tmp_path / "scores.jsonl")
    vectors = restored.features(["task1 good", "task2 bad"])
    assert len(vectors) == 2 and all(len(vector) == 2 for vector in vectors)
    assert restored.features([]) == []
    assert restored.score([]) == []
    assert restored.score(["task1 good"])[0] == pytest.approx(rows[0]["score"], abs=1e-6)
    assert vectors[0] == pytest.approx(rows[0]["features"], abs=1e-6)
    assert rows[0]["feature_version"] == manifest["feature_version"]
    head = {
        "feature_version": manifest["feature_version"],
        "manifest_digest": manifest["manifest_digest"],
        "global_weights": manifest["global_head"]["weights"],
        "residual_weights": [0.1, -0.1],
    }
    expected = np.dot(vectors[0], np.asarray(head["global_weights"]) + head["residual_weights"])
    assert restored.score(["task1 good"], head=head)[0] == pytest.approx(expected, abs=1e-6)
    with pytest.raises(ValueError, match="different shared"):
        restored.score(["task1 good"], head={**head, "feature_version": "another-basis"})
    with pytest.raises(ValueError, match="different shared"):
        restored.score(["task1 good"], head={**head, "manifest_digest": "another-manifest"})
    assert (tmp_path / "model" / "action_reward_stats.json").exists()
    assert len(basis_train.read_jsonl(tmp_path / "action_scores.jsonl")) == 1
    # An immutable encoder artifact is retained unchanged, not a fine-tuned encoder.
    transformers = pytest.importorskip("transformers")
    original = transformers.AutoModelForSequenceClassification.from_pretrained(
        tiny_encoder, local_files_only=True
    )
    for name, parameter in original.named_parameters():
        assert torch.equal(parameter, dict(restored.model.named_parameters())[name])


def test_anchor_equivalence_uses_classifier_pooling_and_survives_reload(
    tmp_path, monkeypatch, tiny_encoder
):
    torch = pytest.importorskip("torch")
    from rm_worker import basis, basis_train
    from rm_worker.scoring import score_texts

    monkeypatch.setattr(basis, "pick_device", lambda: torch.device("cpu"))
    make_job(tmp_path, tiny_encoder, monkeypatch)
    basis_train.train(tmp_path)
    restored = basis.BasisRewardModel(tmp_path / "model")
    texts = ["task1 good", "task2 bad task3", "task4 good [PAD]"]
    for padding in ("left", "right"):
        restored.tokenizer.padding_side = padding
        original = score_texts(
            restored.model, restored.tokenizer, texts, restored.device, batch_size=3
        )
        assert restored.score(texts) == pytest.approx(original, abs=1e-6)
        assert [row[0] for row in restored.features(texts)] == pytest.approx(original, abs=1e-6)


def test_normalized_anchor_map_preserves_scalar_prior_and_bias_while_learning_residuals():
    torch = pytest.importorskip("torch")
    from rm_worker.basis_train import fit_basis

    torch.set_num_threads(1)
    embeddings = np.asarray(
        [[2, 5], [1, 4], [3, 7], [2, 6], [3, 2], [2, 3], [4, 1], [3, 2]], dtype=np.float32
    )
    anchor = {"weights": np.asarray([0.5, 0.1], dtype=np.float32), "bias": 1.25}
    fitted = fit_basis(
        embeddings, ["a", "a", "b", "b"], dimension=2, steps=40, pretrained_head=anchor
    )
    features = ((embeddings - fitted["mean"]) / fitted["scale"]) @ fitted["projection"].T + fitted[
        "offsets"
    ]
    original = embeddings @ anchor["weights"] + anchor["bias"]
    assert features[:, 0] == pytest.approx(original, abs=1e-6)
    assert features @ fitted["default_weights"] == pytest.approx(original, abs=1e-6)
    assert fitted["default_weights"] == [1.0, 0.0]
    assert fitted["fitting_audit"]["trainable_default_parameters"] == 0
    assert fitted["fitting_audit"]["trainable_basis_parameters"] == 2
    assert fitted["fitting_audit"]["projection_changed"]
    candidate = fit_basis(
        embeddings,
        ["a", "a", "b", "b"],
        dimension=2,
        steps=40,
        pretrained_head=anchor,
        fit_global_residual=True,
    )
    assert candidate["fitting_audit"]["global_residual_fitted"]
    assert not candidate["fitting_audit"]["default_is_pretrained_anchor"]
    assert candidate["fitting_audit"]["trainable_default_parameters"] == 2


def test_anchor_rejects_nonlinear_pooling_or_multiple_reward_outputs():
    pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    from rm_worker.basis import linear_pretrained_head

    bert = transformers.BertForSequenceClassification(
        transformers.BertConfig(
            vocab_size=16,
            hidden_size=8,
            intermediate_size=16,
            num_hidden_layers=1,
            num_attention_heads=1,
            num_labels=1,
        )
    )
    with pytest.raises(ValueError, match="supported decoder"):
        linear_pretrained_head(bert)
    qwen = transformers.Qwen3ForSequenceClassification(
        transformers.Qwen3Config(
            vocab_size=16,
            hidden_size=8,
            intermediate_size=16,
            num_hidden_layers=1,
            num_attention_heads=1,
            num_key_value_heads=1,
            num_labels=2,
        )
    )
    with pytest.raises(ValueError, match="scalar score"):
        linear_pretrained_head(qwen)


def test_missing_reward_head_cannot_be_claimed_as_a_pretrained_critic(tiny_encoder):
    transformers = pytest.importorskip("transformers")
    from rm_worker.basis_train import validate_pretrained_loading

    model = transformers.AutoModelForSequenceClassification.from_pretrained(
        tiny_encoder, local_files_only=True
    )
    with pytest.raises(ValueError, match="complete scalar reward checkpoint"):
        validate_pretrained_loading(model, {"missing_keys": ["score.weight"]}, smoke_test=False)
    with pytest.raises(ValueError, match="complete scalar reward checkpoint"):
        validate_pretrained_loading(model, {"unexpected_keys": ["score.bias"]}, smoke_test=False)
    with pytest.raises(ValueError, match="complete scalar reward checkpoint"):
        validate_pretrained_loading(
            model, {"mismatched_keys": [("score.weight", [1, 8], [2, 8])]}, smoke_test=False
        )
    assert validate_pretrained_loading(model, {}, smoke_test=False)[
        "loaded_parameter_keys_complete"
    ]
    assert validate_pretrained_loading(model, {"missing_keys": ["score.weight"]}, smoke_test=True)[
        "smoke_only_missing_parameters_permitted"
    ]


def test_legacy_parameter_files_and_original_feature_hash_reload(
    tmp_path, monkeypatch, tiny_encoder
):
    torch = pytest.importorskip("torch")
    from rm_worker import basis, basis_train

    monkeypatch.setattr(basis, "pick_device", lambda: torch.device("cpu"))
    make_job(tmp_path, tiny_encoder, monkeypatch)
    basis_train.train(tmp_path)
    directory = tmp_path / "model"
    with np.load(directory / "basis_parameters.npz", allow_pickle=False) as saved:
        legacy = {key: saved[key].copy() for key in ("projection", "mean", "scale")}
    np.savez(directory / "basis_parameters.npz", **legacy)
    manifest_path = directory / "basis_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["input_contract"]["feature_extractor"] = "last_nonpadding_hidden_v1"
    manifest["input_contract"].pop("input_serialization", None)
    manifest["parameters_sha256"] = basis.file_sha256(directory / "basis_parameters.npz")
    # Reconstruct the actual pre-anchor implementation's hash definition.
    import hashlib

    manifest["feature_version"] = hashlib.sha256(
        basis.canonical_json(
            {
                "encoder_sha256": manifest["encoder"]["artifact_sha256"],
                "parameters_sha256": manifest["parameters_sha256"],
                "input_contract": manifest["input_contract"],
                "feature_extractor": "last_nonpadding_hidden_v1",
            }
        )
    ).hexdigest()
    manifest.pop("basis_components")
    manifest["global_head"].pop("strategy")
    manifest["manifest_digest"] = basis.manifest_digest(manifest)
    manifest_path.write_text(json.dumps(manifest))
    restored = basis.BasisRewardModel(directory)
    texts = ["task1 good", "task2 bad [PAD]"]
    hidden = basis.encoder_features(
        restored.model,
        restored.tokenizer,
        texts,
        restored.device,
        feature_extractor="last_nonpadding_hidden_v1",
    )
    expected = ((hidden - legacy["mean"]) / legacy["scale"]) @ legacy["projection"].T
    assert np.asarray(restored.features(texts)) == pytest.approx(expected, abs=1e-6)
    assert restored.offsets.tolist() == [0.0, 0.0]


def test_cloud_feature_receipts_compare_anchor_to_actual_logits(
    tmp_path, monkeypatch, tiny_encoder
):
    torch = pytest.importorskip("torch")
    from rm_worker import basis, basis_features, basis_train

    monkeypatch.setattr(basis, "pick_device", lambda: torch.device("cpu"))
    make_job(tmp_path, tiny_encoder, monkeypatch)
    trained = basis_train.train(tmp_path)
    manifest = trained["metrics"]["basis_manifest"]
    assert manifest["input_contract"]["input_serialization"] == "caller_preformatted_stash_input"
    monkeypatch.setattr(basis_features, "download_model", lambda key, target: tmp_path / "model")
    monkeypatch.setenv(
        "RM_TRAINING_ON_CLOUD_GPU", "1"
    )  # only the explicitly tiny local fixture is loaded
    (tmp_path / "job.json").write_text(
        json.dumps(
            {
                "reward_model_key": "owned-smoke",
                "feature_version": manifest["feature_version"],
                "manifest_digest": manifest["manifest_digest"],
            }
        )
    )
    basis_train.write_jsonl(
        tmp_path / "feature_items.jsonl",
        [{"id": "one", "text": "task1 good"}, {"id": "two", "text": "task2 bad [PAD]"}],
    )
    basis_features.run(tmp_path)
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["anchor_fidelity"]["samples"] == 2
    assert result["anchor_fidelity"]["max_abs_score_delta"] < 1e-6
    assert not result["anchor_fidelity"]["bitwise_equivalence_claimed"]


def test_corrupt_artifact_and_manifest_are_rejected(tmp_path, monkeypatch, tiny_encoder):
    from rm_worker import basis, basis_train

    make_job(tmp_path, tiny_encoder, monkeypatch)
    basis_train.train(tmp_path)
    directory = tmp_path / "model"
    manifest_path = directory / "basis_manifest.json"
    original = manifest_path.read_text()
    manifest = json.loads(original)
    manifest["global_head"]["weights"][0] += 1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest digest"):
        basis.BasisRewardModel(directory)
    manifest_path.write_text(original)
    with (directory / "basis_parameters.npz").open("ab") as output:
        output.write(b"changed")
    with pytest.raises(ValueError, match="does not match its version"):
        basis.BasisRewardModel(directory)


def test_learning_source_profile_differences_requires_more_than_one_scalar():
    torch = pytest.importorskip("torch")
    from rm_worker.basis_train import fit_basis

    torch.set_num_threads(1)
    # Both like +x; they disagree on y. Their desired directions are independent.
    embeddings = np.asarray(
        [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 0], [-1, 0], [0, -1], [0, 1]],
        dtype=np.float32,
    )
    profiles = ["a", "a", "b", "b"]
    fitted = fit_basis(embeddings, profiles, dimension=2, steps=200)
    features = ((embeddings - fitted["mean"]) / fitted["scale"]) @ fitted["projection"].T
    differences = features[::2] - features[1::2]
    source_heads = fitted["source_profile_heads"]
    margins = [np.dot(row, source_heads[profile]) for row, profile in zip(differences, profiles)]
    assert all(margin > 0.5 for margin in margins)
    assert not np.allclose(source_heads["a"], source_heads["b"])
    assert np.linalg.matrix_rank(fitted["projection"]) == 2
    assert fitted["fitting_audit"]["source_profiles_balanced"]


@pytest.mark.parametrize("mutation", ["group", "text", "id", "partition", "profile"])
def test_reject_unfrozen_or_leaking_pairs(tmp_path, monkeypatch, tiny_encoder, mutation):
    from rm_worker import basis_train

    _, pairs, _ = make_job(tmp_path, tiny_encoder, monkeypatch)
    if mutation == "group":
        pairs[-1]["task_group"] = pairs[0]["task_group"]
    elif mutation == "text":
        pairs[-1]["chosen"] = pairs[0]["rejected"]
    elif mutation == "id":
        pairs[-1]["example_id"] = pairs[0]["example_id"]
    elif mutation == "partition":
        pairs[-1]["partition"] = "support"
    else:
        pairs[-1].pop("profile_id")
        pairs[-1].pop("domain")
    basis_train.write_jsonl(tmp_path / "pairs.jsonl", pairs)
    with pytest.raises(ValueError):
        basis_train.train(tmp_path)


def test_cloud_guard_rejects_real_local_encoder_load(tmp_path, monkeypatch):
    from rm_worker import basis_train

    job, _, _ = make_job(tmp_path, "Skywork/Skywork-Reward-V2-Qwen3-4B", monkeypatch)
    job["smoke_test"] = False
    (tmp_path / "job.json").write_text(json.dumps(job))
    monkeypatch.delenv("RM_TRAINING_ON_CLOUD_GPU", raising=False)
    with pytest.raises(RuntimeError, match="must run in the cloud"):
        basis_train.train(tmp_path)


def test_smoke_guard_rejects_large_local_config_before_loading_weights(tmp_path, monkeypatch):
    transformers = pytest.importorskip("transformers")
    from rm_worker import basis_train

    base = tmp_path / "large-local-config"
    base.mkdir()
    transformers.BertConfig(hidden_size=768).save_pretrained(base)
    make_job(tmp_path, base, monkeypatch)

    def never_load(*args, **kwargs):
        pytest.fail("Smoke guard must reject a large config before weight loading")

    monkeypatch.setattr(
        basis_train.AutoModelForSequenceClassification, "from_pretrained", never_load
    )
    with pytest.raises(ValueError, match="configuration is too large"):
        basis_train.train(tmp_path)
