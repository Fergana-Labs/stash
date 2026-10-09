"""The learnable head over rubric answers: fit, predict, evaluate, gate.

Features are judge probabilities in [0, 1] (spec.feature_names), left
unstandardized so every weight reads directly as "how much this answer moves
the decision" and users can edit weights by hand.

choice:     softmax(W f + b) over the output labels (multinomial logistic).
preference: score = w . f + b. Pairs use P(a beats b) = sigmoid(score_a - score_b)
            (Bradley-Terry; b cancels); good/bad items use sigmoid(score).

All fitting is L-BFGS on a few dozen parameters, so it runs inline in the API.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.special import expit, log_softmax

GATE_LOG_LOSS_SLACK = 0.02
MIN_GATE_EXAMPLES = 4


def answers_to_features(rubric: list[dict], answers: dict[str, dict]) -> list[float]:
    values = []
    for q in rubric:
        probabilities = answers[q["id"]]["probabilities"]
        if q["type"] == "choice":
            values.extend(probabilities[option] for option in q["criteria"])
        elif q["type"] == "noul":
            values.append(probabilities["true"])
        else:
            values.extend(probabilities[str(level)] for level in range(len(q["criteria"])))
    return values


def blank(feature_names: list[str], classes: list[str]) -> dict:
    return {
        "feature_names": feature_names,
        "classes": classes,
        "weights": [[0.0] * len(feature_names) for _ in classes],
        "bias": [0.0] * len(classes),
        "temperature": 1.0,
        "l2": None,
        "edited": False,
        "fit": None,
    }


def is_stale(head: dict | None, feature_names: list[str], classes: list[str]) -> bool:
    return head is None or head["feature_names"] != feature_names or head["classes"] != classes


# ── Rows ─────────────────────────────────────────────────────────────────
# A row is {"kind": "item"|"pair", "f": [...], "f_b": [...]?, "label": str}.


def _choice_logits(head: dict, f: np.ndarray) -> np.ndarray:
    return (np.asarray(head["weights"]) @ f + np.asarray(head["bias"])) / head["temperature"]


def predict_choice(head: dict, features: list[float]) -> dict:
    f = np.asarray(features, dtype=float)
    logits = _choice_logits(head, f)
    probs = np.exp(log_softmax(logits))
    top = int(np.argmax(probs))
    contributions = (np.asarray(head["weights"]) * f) / head["temperature"]
    return {
        "label": head["classes"][top],
        "probabilities": {c: float(p) for c, p in zip(head["classes"], probs)},
        "confidence": float(probs[top]),
        # Contribution of each feature to each label's logit, for explanation.
        "contributions": {
            c: {n: float(v) for n, v in zip(head["feature_names"], row)}
            for c, row in zip(head["classes"], contributions)
        },
    }


def score(head: dict, features: list[float]) -> float:
    w = np.asarray(head["weights"][0])
    return float((w @ np.asarray(features, dtype=float) + head["bias"][0]) / head["temperature"])


def predict_preference_item(head: dict, features: list[float]) -> dict:
    s = score(head, features)
    p_good = float(expit(s))
    w = np.asarray(head["weights"][0]) / head["temperature"]
    return {
        "score": s,
        "label": "good" if p_good >= 0.5 else "bad",
        "probabilities": {"good": p_good, "bad": 1 - p_good},
        "confidence": max(p_good, 1 - p_good),
        "contributions": {
            "score": {n: float(v) for n, v in zip(head["feature_names"], w * np.asarray(features))}
        },
    }


def compare(head: dict, features_a: list[float], features_b: list[float]) -> dict:
    w = np.asarray(head["weights"][0]) / head["temperature"]
    diff = np.asarray(features_a, dtype=float) - np.asarray(features_b, dtype=float)
    p_a = float(expit(w @ diff))
    return {
        "score_a": score(head, features_a),
        "score_b": score(head, features_b),
        "p_a_wins": p_a,
        "winner": "a" if p_a >= 0.5 else "b",
        "confidence": max(p_a, 1 - p_a),
        "contributions": {n: float(v) for n, v in zip(head["feature_names"], w * diff)},
    }


def row_probability(head: dict, output_type: str, row: dict) -> tuple[float, str]:
    """Probability assigned to the row's true label, and the predicted label."""
    if output_type == "choice":
        out = predict_choice(head, row["f"])
        return out["probabilities"][row["label"]], out["label"]
    if row["kind"] == "pair":
        out = compare(head, row["f"], row["f_b"])
        return (out["p_a_wins"] if row["label"] == "a" else 1 - out["p_a_wins"]), out["winner"]
    out = predict_preference_item(head, row["f"])
    return out["probabilities"][row["label"]], out["label"]


# ── Fitting ──────────────────────────────────────────────────────────────


def _choice_loss(theta, X, y, n_cls, l2):
    n_feat = X.shape[1]
    W = theta[: n_cls * n_feat].reshape(n_cls, n_feat)
    b = theta[n_cls * n_feat :]
    logp = log_softmax(X @ W.T + b, axis=1)
    loss = -logp[np.arange(len(y)), y].mean() + 0.5 * l2 * np.sum(W * W)
    p = np.exp(logp)
    p[np.arange(len(y)), y] -= 1
    grad_W = p.T @ X / len(y) + l2 * W
    grad_b = p.mean(axis=0)
    return loss, np.concatenate([grad_W.ravel(), grad_b])


def _preference_loss(theta, D, Xi, yi, l2):
    w, b = theta[:-1], theta[-1]
    n = len(D) + len(Xi)
    loss, grad_w, grad_b = 0.5 * l2 * w @ w, l2 * w, 0.0
    if len(D):
        m = D @ w  # pairs are oriented so the winner is first
        loss += np.logaddexp(0, -m).sum() / n
        grad_w = grad_w - D.T @ expit(-m) / n
    if len(Xi):
        s = Xi @ w + b
        signed = np.where(yi == 1, s, -s)
        loss += np.logaddexp(0, -signed).sum() / n
        coef = -expit(-signed) * np.where(yi == 1, 1, -1) / n
        grad_w = grad_w + Xi.T @ coef
        grad_b = coef.sum()
    return loss, np.concatenate([grad_w, [grad_b]])


def fit(
    output_type: str, feature_names: list[str], classes: list[str], rows: list[dict], l2: float
) -> dict:
    if not rows:
        raise ValueError("No labeled, graded examples to fit")
    n_feat = len(feature_names)
    if output_type == "choice":
        index = {c: i for i, c in enumerate(classes)}
        X = np.asarray([r["f"] for r in rows], dtype=float)
        y = np.asarray([index[r["label"]] for r in rows])
        result = minimize(
            _choice_loss,
            np.zeros(len(classes) * (n_feat + 1)),
            args=(X, y, len(classes), l2),
            jac=True,
            method="L-BFGS-B",
        )
        weights = result.x[: len(classes) * n_feat].reshape(len(classes), n_feat)
        bias = result.x[len(classes) * n_feat :]
        bias = bias - bias.mean()  # softmax is shift-invariant; center for readability
    else:
        pairs = [r for r in rows if r["kind"] == "pair"]
        items = [r for r in rows if r["kind"] == "item"]
        D = np.asarray(
            [np.subtract(r["f"], r["f_b"]) * (1 if r["label"] == "a" else -1) for r in pairs],
            dtype=float,
        ).reshape(len(pairs), n_feat)
        Xi = np.asarray([r["f"] for r in items], dtype=float).reshape(len(items), n_feat)
        yi = np.asarray([1 if r["label"] == "good" else 0 for r in items])
        result = minimize(
            _preference_loss,
            np.zeros(n_feat + 1),
            args=(D, Xi, yi, l2),
            jac=True,
            method="L-BFGS-B",
        )
        weights, bias = result.x[:-1].reshape(1, n_feat), result.x[-1:]
    return {
        "feature_names": feature_names,
        "classes": classes,
        "weights": [[round(float(v), 6) for v in row] for row in weights],
        "bias": [round(float(v), 6) for v in bias],
        "temperature": 1.0,
        "l2": l2,
        "edited": False,
        "fit": {
            "converged": bool(result.success),
            "iterations": int(result.nit),
            "train_rows": len(rows),
        },
    }


def fit_temperature(head: dict, output_type: str, rows: list[dict]) -> float:
    """Single-parameter calibration on held-out rows; 1.0 when there are too few."""
    if len(rows) < MIN_GATE_EXAMPLES:
        return 1.0

    def nll(log_t):
        trial = {**head, "temperature": math.exp(log_t)}
        return -np.mean(
            [math.log(max(row_probability(trial, output_type, r)[0], 1e-9)) for r in rows]
        )

    result = minimize_scalar(nll, bounds=(math.log(0.05), math.log(20)), method="bounded")
    return round(math.exp(result.x), 4)


# ── Evaluation ───────────────────────────────────────────────────────────


def evaluate(head: dict, output_type: str, rows: list[dict]) -> dict:
    if not rows:
        return {
            "n": 0,
            "accuracy": None,
            "log_loss": None,
            "ece": None,
            "confusion": None,
            "rows": [],
        }
    scored = []
    for r in rows:
        p_true, predicted = row_probability(head, output_type, r)
        scored.append((r, p_true, predicted))
    correct = [predicted == r["label"] for r, _, predicted in scored]
    # Expected calibration error over the confidence of the predicted label.
    confidences = []
    for r, p_true, predicted in scored:
        if output_type == "choice":
            confidences.append(predict_choice(head, r["f"])["confidence"])
        else:
            confidences.append(max(p_true, 1 - p_true))
    bins: dict[int, list[tuple[float, bool]]] = {}
    for conf, ok in zip(confidences, correct):
        bins.setdefault(min(int(conf * 10), 9), []).append((conf, ok))
    ece = sum(
        len(v) / len(scored) * abs(np.mean([c for c, _ in v]) - np.mean([o for _, o in v]))
        for v in bins.values()
    )
    reliability = [
        {
            "bin": k,
            "n": len(v),
            "confidence": float(np.mean([c for c, _ in v])),
            "accuracy": float(np.mean([o for _, o in v])),
        }
        for k, v in sorted(bins.items())
    ]
    confusion = None
    if output_type == "choice":
        confusion = {c: dict.fromkeys(head["classes"], 0) for c in head["classes"]}
        for r, _, predicted in scored:
            confusion[r["label"]][predicted] += 1
    return {
        "n": len(scored),
        "accuracy": float(np.mean(correct)),
        "log_loss": float(-np.mean([math.log(max(p, 1e-9)) for _, p, _ in scored])),
        "ece": float(ece),
        "reliability": reliability,
        "confusion": confusion,
        "rows": [
            {
                "example_id": r["example_id"],
                "label": r["label"],
                "predicted": predicted,
                "p_true": p,
            }
            for r, p, predicted in scored
        ],
    }


def gate(candidate: dict, incumbent: dict | None) -> dict:
    """Promotion check on the shared held-out split; mirrors the reward-compiler gate."""
    checks = []
    if candidate["n"] < MIN_GATE_EXAMPLES:
        checks.append(
            {
                "name": "held_out_size",
                "passed": False,
                "detail": f"{candidate['n']} held-out examples; need {MIN_GATE_EXAMPLES}",
            }
        )
    else:
        checks.append(
            {
                "name": "held_out_size",
                "passed": True,
                "detail": f"{candidate['n']} held-out examples",
            }
        )
    if incumbent is not None and incumbent["n"] and candidate["n"]:
        checks.append(
            {
                "name": "accuracy_not_lower",
                "passed": candidate["accuracy"] >= incumbent["accuracy"] - 1e-9,
                "detail": f"{candidate['accuracy']:.3f} vs active {incumbent['accuracy']:.3f}",
            }
        )
        checks.append(
            {
                "name": "log_loss_within_slack",
                "passed": candidate["log_loss"] <= incumbent["log_loss"] + GATE_LOG_LOSS_SLACK,
                "detail": f"{candidate['log_loss']:.3f} vs active {incumbent['log_loss']:.3f} (+{GATE_LOG_LOSS_SLACK})",
            }
        )
    return {"passed": all(c["passed"] for c in checks), "checks": checks}
