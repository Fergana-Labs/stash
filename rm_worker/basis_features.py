"""Generate private, version-pinned customer features on the cloud worker."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from rm_worker.artifacts import download_model
from rm_worker.basis_manifest import validate_features, validate_manifest


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def run(directory: Path) -> None:
    if os.environ.get("RM_TRAINING_ON_CLOUD_GPU") != "1":
        raise RuntimeError("Reward basis feature extraction must run in the cloud")
    from rm_worker.basis import BasisRewardModel

    job = json.loads((directory / "job.json").read_text())
    items = [
        json.loads(line) for line in (directory / "feature_items.jsonl").read_text().splitlines()
    ]
    if not 1 <= len(items) <= 500:
        raise ValueError("Feature jobs need between 1 and 500 inputs")
    if any(not isinstance(item.get("text"), str) or not item["text"].strip() for item in items):
        raise ValueError("Feature inputs require nonempty text")
    if sum(len(item["text"]) for item in items) > 2_000_000:
        raise ValueError("Feature input size exceeds the job budget")
    ids = [item.get("id") for item in items]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Feature input IDs must be unique strings")
    model = BasisRewardModel(download_model(job["reward_model_key"], directory / "checkpoint"))
    manifest = validate_manifest(model.manifest)
    if (
        manifest["feature_version"] != job["feature_version"]
        or manifest["manifest_digest"] != job["manifest_digest"]
    ):
        raise ValueError("Stored checkpoint differs from the requested feature version")
    features = model.features([item["text"] for item in items])
    if len(features) != len(items):
        raise ValueError("Feature worker returned the wrong number of inputs")
    rows = [
        {
            "id": item["id"],
            "input_digest": text_digest(item["text"]),
            "feature_version": manifest["feature_version"],
            "manifest_digest": manifest["manifest_digest"],
            "features": validate_features(values, manifest),
        }
        for item, values in zip(items, features, strict=True)
    ]
    (directory / "features.jsonl").write_text(
        "".join(json.dumps(row, allow_nan=False) + "\n" for row in rows)
    )
    fidelity = None
    if manifest.get("basis_components", {}).get("pretrained_anchor", {}).get("enabled"):
        from rm_worker.scoring import score_texts

        count = min(8, len(items))
        logits = score_texts(
            model.model,
            model.tokenizer,
            [item["text"] for item in items[:count]],
            model.device,
            model.batch_size,
        )
        anchor = np.asarray(features, dtype=np.float64)[:count, 0]
        delta = np.abs(anchor - np.asarray(logits, dtype=np.float64))
        fidelity = {
            "samples": count,
            "max_abs_score_delta": float(delta.max()),
            "max_scale_normalized_delta": float((delta / np.maximum(1.0, np.abs(logits))).max()),
            "comparison": "actual_frozen_classifier_logits_vs_exported_anchor",
            "numerical_precision": str(model.model.dtype),
            "bitwise_equivalence_claimed": False,
        }
    (directory / "result.json").write_text(
        json.dumps({"basis_manifest": manifest, "anchor_fidelity": fidelity}, allow_nan=False)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", type=Path, required=True)
    run(parser.parse_args().job_dir)
