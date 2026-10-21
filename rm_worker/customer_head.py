"""Small customer residual heads; no backbone training or model downloads.

The probabilities below are Bradley–Terry model estimates, not calibrated
confidence or probabilities of task success. Empty feedback uses the global head.
"""

import math

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

MAX_DIMENSION = 64
MAX_PAIRS = 1000


def vector(value, dimension=None):
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= MAX_DIMENSION:
        raise ValueError("Features must be a bounded nonempty vector")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("Features must contain finite numbers")
    if dimension is not None and len(value) != dimension:
        raise ValueError("Feature dimension does not match the shared basis")
    return np.asarray(value, dtype=float)


def _pin(value, feature_version, manifest_digest):
    if (
        value.get("feature_version") != feature_version
        or value.get("manifest_digest") != manifest_digest
    ):
        raise ValueError("Customer features/head belong to another shared basis")


def fit_customer_head(pairs, global_weights, *, feature_version, manifest_digest, l2=1.0):
    if not isinstance(pairs, list) or len(pairs) > MAX_PAIRS:
        raise ValueError("Too many customer comparisons")
    if type(l2) not in (int, float) or not math.isfinite(l2) or l2 < 0.001:
        raise ValueError("Customer heads require positive regularization")
    if not all(isinstance(v, str) and len(v) == 64 for v in (feature_version, manifest_digest)):
        raise ValueError("A customer head requires exact shared feature and manifest hashes")
    try:
        int(feature_version, 16)
        int(manifest_digest, 16)
    except ValueError as exc:
        raise ValueError(
            "A customer head requires exact shared feature and manifest hashes"
        ) from exc
    global_w = vector(global_weights)
    differences = []
    for pair in pairs:
        _pin(pair, feature_version, manifest_digest)
        difference = vector(pair["chosen"], len(global_w)) - vector(pair["rejected"], len(global_w))
        if not np.isfinite(difference).all():
            raise ValueError("Customer feature difference is not finite")
        differences.append(difference)
    delta = np.zeros(len(global_w))
    iterations = 0
    if differences:
        differences = np.asarray(differences)

        def objective(residual):
            margin = differences @ (global_w + residual)
            loss = np.logaddexp(0, -margin).mean() + 0.5 * l2 * (residual @ residual)
            gradient = -differences.T @ expit(-margin) / len(differences) + l2 * residual
            return float(loss), gradient

        result = minimize(objective, delta, jac=True, method="L-BFGS-B")
        if not result.success or not np.isfinite(result.x).all():
            raise ValueError("Customer head fitting did not converge")
        delta = result.x
        iterations = int(result.nit)
    return {
        "feature_version": feature_version,
        "manifest_digest": manifest_digest,
        "global_weights": global_w.tolist(),
        "residual_weights": delta.tolist(),
        "fit": {"pairs": len(pairs), "l2": l2, "iterations": iterations},
        "calibrated": False,
    }


def score_features(features, head, *, feature_version, manifest_digest):
    _pin(head, feature_version, manifest_digest)
    global_w = vector(head["global_weights"])
    delta = vector(head["residual_weights"], len(global_w))
    score = float(vector(features, len(global_w)) @ (global_w + delta))
    if not math.isfinite(score):
        raise ValueError("Customer score is not finite")
    return score


def compare_features(a, b, head, *, feature_version, manifest_digest):
    kwargs = {"feature_version": feature_version, "manifest_digest": manifest_digest}
    score_a = score_features(a, head, **kwargs)
    score_b = score_features(b, head, **kwargs)
    return {
        "score_a": score_a,
        "score_b": score_b,
        "p_a_wins": float(expit(score_a - score_b)),
        "calibrated": False,
    }
