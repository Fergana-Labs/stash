"""Tiny regularized linear readout. No pretrained model or generation lives here."""

from __future__ import annotations

import math

RIDGE = 0.01  # Fixed before any development/test inspection; no test-set tuning.


def fit(rows):
    import numpy as np
    from scipy.optimize import minimize

    train = [r for r in rows if r["partition"] == "train"]
    if len(train) < 4 or {r["label"] for r in train} != {"liked", "disliked"}:
        raise ValueError("Need both labels and at least four training examples")
    x = np.asarray([r["activation"] for r in train], dtype=np.float64)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("Non-finite or inconsistent activations")
    x /= np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)
    center = x.mean(axis=0)
    x -= center
    y = np.asarray([1.0 if r["label"] == "liked" else -1.0 for r in train])
    sample_weights = np.asarray([1 / (2 * sum(y == label)) for label in y])

    def objective(theta):
        w, b = theta[:-1], theta[-1]
        z = y * (x @ w + b)
        loss = (sample_weights * np.logaddexp(0, -z)).sum() + RIDGE * (w @ w) / 2
        grad_z = -sample_weights * y / (1 + np.exp(np.clip(z, -500, 500)))
        return loss, np.r_[x.T @ grad_z + RIDGE * w, grad_z.sum()]

    result = minimize(objective, np.zeros(x.shape[1] + 1), method="L-BFGS-B", jac=True)
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("Linear head fit did not converge")
    return {
        "method": "class-balanced L2 logistic linear probe",
        "ridge": RIDGE,
        "weights": result.x[:-1].tolist(),
        "bias": float(result.x[-1]),
        "center": center.tolist(),
        "dimensions": x.shape[1],
        "train_ids": [r["id"] for r in train],
        "calibrated": False,
    }


def predict(head, activation):
    if len(activation) != head["dimensions"] or not all(math.isfinite(v) for v in activation):
        raise ValueError("Activation shape or values differ from the frozen head")
    norm = math.sqrt(sum(v * v for v in activation)) or 1
    logit = head["bias"] + sum(
        w * (v / norm - c) for w, v, c in zip(head["weights"], activation, head["center"])
    )
    score = 1 / (1 + math.exp(-max(-500, min(500, logit))))
    return {
        "label": "liked" if logit >= 0 else "disliked",
        "score": score,
        "raw_logit": logit,
        "calibrated": False,
        "interpretation": "Uncalibrated sigmoid readout, not probability of human approval",
    }


def metrics(head, rows):
    results = [{"id": r["id"], "truth": r["label"], **predict(head, r["activation"])} for r in rows]
    per_class = {}
    for label in ("liked", "disliked"):
        subset = [r for r in results if r["truth"] == label]
        per_class[label] = {
            "n": len(subset),
            "recall": sum(r["label"] == label for r in subset) / len(subset) if subset else None,
        }
    return {
        "n": len(results),
        "accuracy": sum(r["label"] == r["truth"] for r in results) / len(results)
        if results
        else None,
        "per_class": per_class,
        "rows": results,
    }


def release_gate(dataset, reports):
    dev, test = reports["dev"], reports["test"]
    human = all(e["supervision"].get("human_reviewed") is True for e in dataset["examples"])
    checks = {
        "human_reviewed_labels": human,
        "fresh_human_holdout": dataset.get("heldout_status") == "untouched_human_test",
        "development_both_classes": all(
            c["n"] >= 2 and (c["recall"] or 0) >= 0.5 for c in dev["per_class"].values()
        ),
        "development_agreement": dev["n"] >= 4 and (dev["accuracy"] or 0) >= 0.75,
        "test_both_classes": all(
            c["n"] >= 2 and (c["recall"] or 0) >= 0.5 for c in test["per_class"].values()
        ),
        "test_agreement": test["n"] >= 6 and (test["accuracy"] or 0) >= 0.75,
    }
    return {"passed": all(checks.values()), "checks": checks}
