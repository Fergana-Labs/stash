"""Cloud shared reward-basis fitting over frozen encoder representations.

Local execution is restricted to explicit smoke tests with local random models
under 20K parameters. No external checkpoint is loaded by those tests.
"""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoConfig, AutoModelForSequenceClassification

from rm_worker.artifacts import upload_model
from rm_worker.basis import (
    EVALUATOR_KIND,
    FEATURE_EXTRACTOR,
    canonical_json,
    directory_sha256,
    encoder_features,
    feature_version,
    file_sha256,
    linear_pretrained_head,
    manifest_digest,
)
from rm_worker.evaluation import action_reference_rewards, action_score_rows, reward_stats
from rm_worker.progress import Reporter
from rm_worker.release_gate import check_partition
from rm_worker.scoring import load_tokenizer, pick_device


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows))


def validate_pairs(pairs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fail closed on unfrozen partitions or trace/example leakage."""
    ids = set()
    for pair in pairs:
        for key in ("example_id", "task_group", "chosen", "rejected", "partition"):
            if not isinstance(pair.get(key), str) or not pair[key].strip():
                raise ValueError(f"Basis pair requires nonempty {key}")
        if pair["example_id"] in ids:
            raise ValueError("Basis examples must have unique example_id values")
        ids.add(pair["example_id"])
        if pair["chosen"] == pair["rejected"]:
            raise ValueError("Basis preference alternatives must differ")
        for key in ("profile_id", "domain", "customer_id", "workflow_id"):
            if key in pair and (not isinstance(pair[key], str) or not pair[key].strip()):
                raise ValueError(f"Basis pair has invalid {key}")
        if not pair.get("profile_id") and not pair.get("domain"):
            raise ValueError("Basis pair needs profile_id or domain for shared preference learning")
    return check_partition(pairs)


def pair_profile(pair: dict) -> str:
    return pair.get("profile_id") or pair["domain"]


def validate_pretrained_loading(model, loading_info: dict, *, smoke_test: bool) -> dict:
    """A newly initialized ``score`` layer is not a pretrained reward critic."""
    parameter_names = {name for name, _ in model.named_parameters()}
    missing = [key for key in loading_info.get("missing_keys", []) if key in parameter_names]
    mismatched = [
        entry[0] if isinstance(entry, (list, tuple)) else entry
        for entry in loading_info.get("mismatched_keys", [])
    ]
    dropped_head = [
        key for key in loading_info.get("unexpected_keys", []) if key.startswith("score.")
    ]
    if not smoke_test and (missing or mismatched or dropped_head):
        raise ValueError(
            "Shared pretrained anchor requires a complete scalar reward checkpoint; initialized, mismatched or dropped parameters cannot be used as a pretrained critic"
        )
    return {
        "loaded_parameter_keys_complete": not missing and not mismatched,
        "missing_parameter_keys": missing,
        "mismatched_parameter_keys": mismatched,
        "dropped_score_keys": dropped_head,
        "smoke_only_missing_parameters_permitted": smoke_test
        and bool(missing or mismatched or dropped_head),
    }


def fit_basis(
    embeddings: np.ndarray,
    profiles: list[str],
    *,
    dimension: int,
    steps: int = 200,
    learning_rate: float = 0.01,
    l2: float = 0.05,
    seed: int = 0,
    device=None,
    on_progress=None,
    pretrained_head: dict | None = None,
    fit_global_residual: bool = False,
) -> dict:
    """Jointly learn basis, population weights, and source-profile residuals.

    Inputs alternate chosen/rejected. Only source training pairs may be passed.
    Source profiles receive equal aggregate weight, so a prolific profile does
    not silently determine the default. An orthogonality penalty discourages
    redundant scalar copies; it does not assert semantic interpretability.
    """
    values = np.asarray(embeddings, dtype=np.float32)
    if (
        values.ndim != 2
        or values.shape[0] != 2 * len(profiles)
        or len(profiles) < 2
        or not np.isfinite(values).all()
    ):
        raise ValueError("Basis fitting requires finite paired encoder embeddings")
    if type(dimension) is not int or not 1 <= dimension <= min(64, values.shape[1]):
        raise ValueError("Invalid reward basis dimension")
    if (
        type(steps) is not int
        or steps < 1
        or not np.isfinite(learning_rate)
        or learning_rate <= 0
        or not np.isfinite(l2)
        or l2 < 0.001
    ):
        raise ValueError("Invalid basis fitting hyperparameters")
    torch.manual_seed(seed)
    device = device or torch.device("cpu")
    mean = values.mean(axis=0)
    scale = np.maximum(values.std(axis=0), 1e-6)
    anchored = pretrained_head is not None
    anchor_projection = None
    offsets = np.zeros(dimension, dtype=np.float32)
    if anchored:
        anchor_weights = np.asarray(pretrained_head["weights"], dtype=np.float32)
        bias = pretrained_head.get("bias", 0.0)
        if (
            anchor_weights.shape != (values.shape[1],)
            or not np.isfinite(anchor_weights).all()
            or not np.isfinite(bias)
            or not np.any(anchor_weights)
        ):
            raise ValueError("Invalid pretrained head for encoder embeddings")
        # h = normalized * scale + mean. This row plus offset reproduces w.h+b.
        anchor_projection = torch.as_tensor((anchor_weights * scale)[None, :], device=device)
        offsets[0] = np.dot(anchor_weights, mean) + bias
    if type(fit_global_residual) is not bool:
        raise ValueError("fit_global_residual must be boolean")
    normalized = torch.as_tensor((values - mean) / scale, device=device)
    differences = normalized[0::2] - normalized[1::2]
    names = sorted(set(profiles))
    indices = torch.tensor([names.index(name) for name in profiles], device=device)
    counts = Counter(profiles)
    pair_weights = torch.tensor(
        [1 / (len(names) * counts[name]) for name in profiles], device=device
    )
    residual_dimension = dimension - int(anchored)
    projection = torch.nn.Parameter(torch.empty(residual_dimension, values.shape[1], device=device))
    if residual_dimension:
        torch.nn.init.orthogonal_(projection)
        if anchored:
            with torch.no_grad():
                anchor_direction = F.normalize(anchor_projection, dim=1)
                projection -= (projection @ anchor_direction.T) @ anchor_direction
    initial_projection = projection.detach().clone()
    prior = torch.zeros(dimension, device=device)
    if anchored:
        prior[0] = 1
    default_residual = torch.nn.Parameter(
        torch.zeros(dimension, device=device), requires_grad=not anchored or fit_global_residual
    )
    residuals = torch.nn.Parameter(torch.zeros(len(names), dimension, device=device))
    trainable = [projection, residuals]
    if default_residual.requires_grad:
        trainable.append(default_residual)
    optimizer = torch.optim.AdamW(trainable, lr=learning_rate, weight_decay=0)
    for step in range(steps):
        full_projection = (
            torch.cat((anchor_projection, projection), dim=0) if anchored else projection
        )
        default = prior + default_residual
        features = differences @ full_projection.T
        global_margins = features @ default
        profile_margins = (features * (default + residuals[indices])).sum(dim=1)
        global_loss = (F.softplus(-global_margins) * pair_weights).sum()
        profile_loss = (F.softplus(-profile_margins) * pair_weights).sum()
        orthogonal_rows = (
            torch.cat((F.normalize(anchor_projection, dim=1), projection), dim=0)
            if anchored
            else projection
        )
        distinct = orthogonal_rows @ orthogonal_rows.T - torch.eye(dimension, device=device)
        regularization = l2 * (default_residual.square().mean() + residuals.square().mean())
        if residual_dimension:
            regularization = regularization + l2 * (projection - initial_projection).square().mean()
        loss = global_loss + profile_loss + regularization + 0.01 * distinct.square().mean()
        if not torch.isfinite(loss):
            raise ValueError("Shared basis optimization produced non-finite loss")
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        if on_progress:
            on_progress(step + 1, steps)
    full_projection = torch.cat((anchor_projection, projection), dim=0) if anchored else projection
    default = prior + default_residual
    projection_value = full_projection.detach().cpu().numpy()
    default_value = default.detach().cpu().numpy()
    source_heads = {
        name: (default + residuals[index]).detach().cpu().tolist()
        for index, name in enumerate(names)
    }
    return {
        "projection": projection_value,
        "mean": mean,
        "scale": scale,
        "offsets": offsets,
        "default_weights": default_value.tolist(),
        "source_profile_heads": source_heads,
        "fitting_audit": {
            "fit_pairs": len(profiles),
            "source_profiles": len(names),
            "heterogeneous_profile_training": len(names) > 1,
            "source_profile_counts": dict(counts),
            "source_profiles_balanced": True,
            "trainable_basis_parameters": int(projection.numel()),
            "trainable_default_parameters": int(default_residual.numel())
            if default_residual.requires_grad
            else 0,
            "trainable_source_profile_parameters": int(residuals.numel()),
            "projection_changed": not torch.equal(initial_projection, projection),
            "fit_steps": steps,
            "learning_rate": learning_rate,
            "l2": l2,
            "seed": seed,
            "final_loss": float(loss.detach().cpu()),
            "semantic_dimensions_validated": False,
            "pretrained_anchor_preserved": anchored,
            "default_is_pretrained_anchor": anchored and not fit_global_residual,
            "global_residual_fitted": anchored and fit_global_residual,
            "learned_residual_dimensions": residual_dimension,
        },
    }


def train(job_dir: Path) -> dict:
    started = time.monotonic()
    progress = Reporter()
    progress.update("loading")
    job = json.loads((job_dir / "job.json").read_text())
    if job.get("kind") != "basis_train" or not job.get("fixed_split"):
        raise ValueError("Shared basis training requires kind=basis_train and fixed_split=true")
    pairs = read_jsonl(job_dir / "pairs.jsonl")
    train_pairs, eval_pairs = validate_pairs(pairs)
    options = job.get("basis_options", {})
    if not isinstance(options, dict):
        raise ValueError("basis_options must be an object")
    for key, default, maximum in (
        ("basis_dimension", 4, 64),
        ("fit_steps", 200, 10_000),
        ("batch_size", 4, 64),
    ):
        value = options.get(key, default)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"Invalid reward basis {key}")
    for key, default, minimum in (("projection_learning_rate", 0.01, 0), ("l2", 0.05, 0.001)):
        value = options.get(key, default)
        if type(value) not in (int, float) or not np.isfinite(value) or value < minimum:
            raise ValueError(f"Invalid reward basis {key}")
        if key == "projection_learning_rate" and value == 0:
            raise ValueError("Invalid reward basis projection_learning_rate")
    seed = options.get("seed", 0)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Invalid reward basis seed")
    smoke_test = job.get("smoke_test") is True
    base_model = job["base_model"]
    if smoke_test:
        if not Path(base_model).is_dir() or len(pairs) > 100:
            raise ValueError(
                "Local basis smoke tests require a tiny local model and at most 100 pairs"
            )
        bounded_inputs = [pair[key] for pair in pairs for key in ("chosen", "rejected")]
        for filename in ("score_items.jsonl", "action_score_items.jsonl"):
            bounded_inputs.extend(item["text"] for item in read_jsonl(job_dir / filename))
        if len(bounded_inputs) > 500 or sum(map(len, bounded_inputs)) > 100_000:
            raise ValueError("Local basis smoke test input budget is too large")
        config = AutoConfig.from_pretrained(base_model, local_files_only=True)
        # Inspect config before touching weight files. The meta construction
        # counts parameters without allocating any model tensors on this Mac.
        if (
            getattr(config, "hidden_size", 0) > 32
            or getattr(config, "num_hidden_layers", 0) > 4
            or getattr(config, "vocab_size", 0) > 256
        ):
            raise ValueError("Local basis smoke test encoder configuration is too large")
        with torch.device("meta"):
            empty_encoder = AutoModelForSequenceClassification.from_config(config)
        if sum(parameter.numel() for parameter in empty_encoder.parameters()) >= 20_000:
            raise ValueError("Local basis smoke test encoder must have fewer than 20K parameters")
        del empty_encoder
    elif os.environ.get("RM_TRAINING_ON_CLOUD_GPU") != "1":
        raise RuntimeError("Substantive reward basis training must run in the cloud")
    if not smoke_test and not job.get("base_model_license"):
        raise ValueError("Cloud reward basis training requires recorded base_model_license")
    device = torch.device("cpu") if smoke_test else pick_device()
    max_length = options.get("max_length", 4096)
    if type(max_length) is not int or not 1 <= max_length <= (128 if smoke_test else 16384):
        raise ValueError("Invalid reward basis context length")
    input_version = job.get("input_version", 1)
    rubric = job.get("rubric", [])
    if type(input_version) is not int or input_version not in (1, 2, 3):
        raise ValueError("Invalid reward basis input version")
    if not isinstance(rubric, list) or any(not isinstance(item, str) for item in rubric):
        raise ValueError("Invalid reward basis rubric")
    tokenizer = load_tokenizer(
        base_model,
        max_length,
        input_version,
        rubric,
        revision=job.get("base_model_revision"),
        local_files_only=smoke_test,
    )
    dtype = (
        torch.bfloat16
        if device.type == "cuda" and torch.cuda.is_bf16_supported()
        else torch.float32
    )
    encoder, loading_info = AutoModelForSequenceClassification.from_pretrained(
        base_model,
        revision=job.get("base_model_revision"),
        local_files_only=smoke_test,
        dtype=dtype,
        output_loading_info=True,
    )
    loading_audit = validate_pretrained_loading(encoder, loading_info, smoke_test=smoke_test)
    parameter_count = sum(parameter.numel() for parameter in encoder.parameters())
    if smoke_test and parameter_count >= 20_000:
        raise ValueError("Local basis smoke test encoder must have fewer than 20K parameters")
    encoder.config.pad_token_id = tokenizer.pad_token_id
    encoder.config.use_cache = False
    encoder.config.stash_training_precision = "bf16" if dtype == torch.bfloat16 else "float32"
    encoder.requires_grad_(False)
    encoder.eval()
    encoder.to(device)
    fit_global_residual = options.get("fit_global_residual", False)
    if type(fit_global_residual) is not bool:
        raise ValueError("Invalid fit_global_residual option")
    try:
        pretrained_head = linear_pretrained_head(encoder)
    except ValueError:
        if not (smoke_test and options.get("allow_unanchored_smoke") is True):
            raise
        pretrained_head = None
    versions = {name: parameter._version for name, parameter in encoder.named_parameters()}
    batch_size = options.get("batch_size", 4)
    train_embeddings = encoder_features(
        encoder,
        tokenizer,
        [pair[key] for pair in train_pairs for key in ("chosen", "rejected")],
        device,
        batch_size,
    )
    progress.update("training", 0, options.get("fit_steps", 200))
    fitted = fit_basis(
        train_embeddings,
        [pair_profile(pair) for pair in train_pairs],
        dimension=options.get("basis_dimension", 4),
        steps=options.get("fit_steps", 200),
        learning_rate=options.get("projection_learning_rate", 0.01),
        l2=options.get("l2", 0.05),
        seed=options.get("seed", 0),
        device=device,
        on_progress=lambda completed, total: progress.update("training", completed, total),
        pretrained_head=pretrained_head,
        fit_global_residual=fit_global_residual,
    )
    if any(parameter._version != versions[name] for name, parameter in encoder.named_parameters()):
        raise RuntimeError("Shared basis fitting modified the frozen encoder")

    def features(texts):
        embeddings = encoder_features(encoder, tokenizer, texts, device, batch_size)
        return ((embeddings - fitted["mean"]) / fitted["scale"]) @ fitted["projection"].T + fitted[
            "offsets"
        ]

    weights = np.asarray(fitted["default_weights"], dtype=np.float32)

    def scores(texts):
        return (features(texts) @ weights).tolist()

    progress.update("evaluating")
    eval_features = features([pair[key] for pair in eval_pairs for key in ("chosen", "rejected")])
    eval_scores = (eval_features @ weights).tolist()
    anchor_scores = eval_features[:, 0].tolist() if pretrained_head is not None else None
    predictions = [
        {
            "example_id": pair["example_id"],
            "chosen_score": eval_scores[2 * index],
            "rejected_score": eval_scores[2 * index + 1],
            "correct": bool(eval_scores[2 * index] > eval_scores[2 * index + 1]),
        }
        for index, pair in enumerate(eval_pairs)
    ]
    if anchor_scores is not None:
        for index, prediction in enumerate(predictions):
            prediction.update(
                pretrained_chosen_score=anchor_scores[2 * index],
                pretrained_rejected_score=anchor_scores[2 * index + 1],
                pretrained_correct=bool(anchor_scores[2 * index] > anchor_scores[2 * index + 1]),
            )
    write_jsonl(job_dir / "evaluation.jsonl", predictions)
    (job_dir / "evaluation.json").write_text(json.dumps(predictions, allow_nan=False))
    model_dir = job_dir / "model"
    model_dir.mkdir(exist_ok=True)
    progress.update("saving")
    encoder.save_pretrained(model_dir / "encoder")
    tokenizer.save_pretrained(model_dir / "encoder")
    np.savez(
        model_dir / "basis_parameters.npz",
        projection=fitted["projection"],
        mean=fitted["mean"],
        scale=fitted["scale"],
        offsets=fitted["offsets"],
    )
    encoder_hash = directory_sha256(model_dir / "encoder")
    parameter_hash = file_sha256(model_dir / "basis_parameters.npz")
    contract = {
        "input_version": input_version,
        "rubric": rubric,
        "max_length": max_length,
        "context_policy": "section_budgets" if input_version == 3 else "left_truncation",
        "feature_extractor": FEATURE_EXTRACTOR,
        "input_serialization": job.get("input_serialization", "caller_preformatted_stash_input"),
    }
    if (
        not isinstance(contract["input_serialization"], str)
        or not contract["input_serialization"].strip()
    ):
        raise ValueError("Input serialization must be an explicit nonempty string")
    fitting_audit = {
        **fitted["fitting_audit"],
        **loading_audit,
        "encoder_parameters": parameter_count,
        "optimized_encoder_parameters": 0,
        "encoder_frozen": True,
        "encoder_tensor_versions_unchanged": True,
        "normalizer_partition": "train",
        "basis_fit_partition": "train",
        "evaluation_used_for_fitting": False,
        "profile_field": "profile_id_or_domain",
        "customer_field": "explicit_customer_id_only",
        "workflow_field": "workflow_id_or_domain",
    }
    manifest = {
        "schema_version": 1,
        "evaluator_kind": EVALUATOR_KIND,
        "basis_dimension": fitted["projection"].shape[0],
        "feature_version": feature_version(encoder_hash, parameter_hash, contract),
        "parameters_sha256": parameter_hash,
        "input_contract": contract,
        "global_head": {
            "weights": fitted["default_weights"],
            "strategy": "pretrained_anchor_only"
            if fitted["fitting_audit"]["default_is_pretrained_anchor"]
            else "regularized_pretrained_plus_learned_residual"
            if pretrained_head is not None
            else "unanchored_smoke_only",
        },
        "basis_components": {
            "pretrained_anchor": {
                "enabled": pretrained_head is not None,
                "feature_index": 0 if pretrained_head is not None else None,
                "head_name": pretrained_head["head_name"] if pretrained_head is not None else None,
                "model_type": pretrained_head["model_type"]
                if pretrained_head is not None
                else None,
                "score_mapping": "normalizer_scaled_linear_head_plus_mean_and_bias_offset"
                if pretrained_head is not None
                else None,
                "frozen": True,
            },
            "learned_residual_feature_indices": list(
                range(int(pretrained_head is not None), fitted["projection"].shape[0])
            ),
            "default_uses_learned_residual": fitted["fitting_audit"]["global_residual_fitted"],
        },
        "encoder": {
            "base_model": base_model,
            "requested_revision": job.get("base_model_revision"),
            "resolved_revision": getattr(encoder.config, "_commit_hash", None),
            "license": job.get("base_model_license", "not_recorded"),
            "artifact_sha256": encoder_hash,
            "frozen": True,
        },
        "training_lineage": {
            # A profile may be a criterion or synthetic user, so it must never
            # silently become an asserted real customer's identity.
            "customer_ids": sorted({p["customer_id"] for p in train_pairs if p.get("customer_id")}),
            "workflow_ids": sorted(
                {
                    p.get("workflow_id") or p["domain"]
                    for p in train_pairs
                    if p.get("workflow_id") or p.get("domain")
                }
            ),
            "profile_ids": sorted({pair_profile(p) for p in train_pairs}),
            "task_groups": sorted({p["task_group"] for p in train_pairs}),
            "example_ids": sorted({p["example_id"] for p in train_pairs}),
            "pairs_sha256": hashlib.sha256(canonical_json(train_pairs)).hexdigest(),
        },
        "fitting_audit": fitting_audit,
    }
    manifest["manifest_digest"] = manifest_digest(manifest)
    (model_dir / "basis_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False))
    (model_dir / "source_profile_heads.json").write_text(
        json.dumps(
            {"training_only": True, "heads": fitted["source_profile_heads"]}, allow_nan=False
        )
    )
    calibration_features = ((train_embeddings - fitted["mean"]) / fitted["scale"]) @ fitted[
        "projection"
    ].T + fitted["offsets"]
    calibration_scores = (calibration_features @ weights).tolist()
    (model_dir / "reward_stats.json").write_text(json.dumps(reward_stats(calibration_scores)))
    progress.update("scoring")
    items = read_jsonl(job_dir / "score_items.jsonl")
    item_features = features([item["text"] for item in items])
    item_scores = (item_features @ weights).tolist()
    write_jsonl(
        job_dir / "scores.jsonl",
        [
            {
                "trace_id": item["trace_id"],
                "score": score,
                "features": vector.tolist(),
                "feature_version": manifest["feature_version"],
                "manifest_digest": manifest["manifest_digest"],
            }
            for item, score, vector in zip(items, item_scores, item_features, strict=True)
        ],
    )
    action_train = [p for p in train_pairs if p.get("granularity") == "action"]
    action_scores = []
    if action_train:
        stats = reward_stats(action_reference_rewards(train_pairs, calibration_scores))
        (model_dir / "action_reward_stats.json").write_text(json.dumps(stats))
        action_items = read_jsonl(job_dir / "action_score_items.jsonl")
        action_scores = action_score_rows(
            action_items, scores([i["text"] for i in action_items]), stats
        )
    write_jsonl(job_dir / "action_scores.jsonl", action_scores)
    progress.update("uploading")
    upload_model(model_dir, job["artifact_key"])
    result = {
        "metrics": {
            "evaluator_kind": EVALUATOR_KIND,
            "basis_manifest": manifest,
            "train_pairs": len(train_pairs),
            "eval_pairs": len(eval_pairs),
            "eval_accuracy": sum(p["correct"] for p in predictions) / len(predictions),
            "pretrained_eval_accuracy": sum(p["pretrained_correct"] for p in predictions)
            / len(predictions)
            if anchor_scores is not None
            else None,
            "paired_wins_over_pretrained": sum(
                p["correct"] and not p["pretrained_correct"] for p in predictions
            )
            if anchor_scores is not None
            else None,
            "paired_losses_to_pretrained": sum(
                not p["correct"] and p["pretrained_correct"] for p in predictions
            )
            if anchor_scores is not None
            else None,
            "default_is_pretrained_anchor": fitted["fitting_audit"]["default_is_pretrained_anchor"],
            "evaluation_claim_scope": "development_pilot; foundation_training_exposure_unknown",
            "eval_split": "curated_task_groups",
            "input_version": input_version,
            "max_length": max_length,
            "context_policy": contract["context_policy"],
            "action_scoring_version": 1 if action_train else None,
            "action_train_pairs": len(action_train),
            "initial_scored_actions": len(action_scores),
            "final_loss": fitting_audit["final_loss"],
            "fit_steps": fitting_audit["fit_steps"],
            "epochs": job.get("epochs"),
            "device": str(device),
            "seconds": round(time.monotonic() - started, 1),
        }
    }
    (job_dir / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a shared frozen-encoder reward basis.")
    parser.add_argument("--job-dir", type=Path, required=True)
    train(parser.parse_args().job_dir)


if __name__ == "__main__":
    main()
