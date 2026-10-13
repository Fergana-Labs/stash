"""Lightweight shared-feature identity checks; safe to import from the API."""

import hashlib
import json
import math
import re

KIND = "shared_basis_v1"


def manifest_digest(manifest: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            {key: value for key, value in manifest.items() if key != "manifest_digest"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def validate_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or manifest.get("evaluator_kind") != KIND:
        raise ValueError("Checkpoint is not a shared reward basis")
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported reward basis manifest version")
    dimension = manifest.get("basis_dimension")
    if type(dimension) is not int or not 1 <= dimension <= 64:
        raise ValueError("Invalid reward basis dimension")
    version = manifest.get("feature_version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{64}", version):
        raise ValueError("Reward basis has no feature version")
    weights = (manifest.get("global_head") or {}).get("weights")
    if not isinstance(weights, list) or len(weights) != dimension:
        raise ValueError("Global head does not match reward basis dimension")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in weights):
        raise ValueError("Global head has invalid weights")
    if manifest.get("manifest_digest") != manifest_digest(manifest):
        raise ValueError("Reward basis manifest digest mismatch")
    return manifest


def validate_features(features: list, manifest: dict) -> list[float]:
    validate_manifest(manifest)
    if not isinstance(features, list) or len(features) != manifest["basis_dimension"]:
        raise ValueError("Features do not match reward basis dimension")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in features):
        raise ValueError("Invalid reward basis features")
    return [float(value) for value in features]
