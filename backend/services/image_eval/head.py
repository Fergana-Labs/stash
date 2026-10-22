"""The trainable part of a taste classifier: a logistic head over frozen image embeddings.

Embeddings are standardized per dimension, then fit with class-balanced L2 logistic
regression by L-BFGS. The L2 strength is chosen by cross-validated log-loss, not
accuracy: accuracy ties favor the strongest regularization, which squashes every
probability toward 0.5 and makes scores useless for ranking. Held-out metrics come
from predicting each example with a head fit without it (leave-one-out for small
sets, stratified 10-fold above that).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_expit

L2_GRID = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0)
MIN_PER_CLASS = 3
LOO_MAX = 60


def _fit(x: np.ndarray, y: np.ndarray, l2: float) -> tuple[np.ndarray, float]:
    """Class-balanced L2 logistic regression; returns (weights, bias)."""
    w_cls = {c: len(y) / (2 * max(1, int((y == c).sum()))) for c in (0, 1)}
    sw = np.where(y == 1, w_cls[1], w_cls[0])
    sign = 2 * y - 1

    def loss(theta):
        w, b = theta[:-1], theta[-1]
        z = x @ w + b
        nll = -(sw * log_expit(sign * z)).sum()
        grad_z = -sw * sign * expit(-sign * z)
        return nll + 0.5 * l2 * w @ w, np.append(x.T @ grad_z + l2 * w, grad_z.sum())

    res = minimize(
        loss, np.zeros(x.shape[1] + 1), jac=True, method="L-BFGS-B", options={"maxiter": 500}
    )
    return res.x[:-1], float(res.x[-1])


def _folds(y: np.ndarray, k: int, seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    folds: list[list[int]] = [[] for _ in range(k)]
    for c in (0, 1):
        idx = rng.permutation(np.flatnonzero(y == c))
        for i, j in enumerate(idx):
            folds[i % k].append(int(j))
    return [np.array(f, dtype=int) for f in folds if f]


def _choose_l2(x: np.ndarray, y: np.ndarray) -> float:
    k = min(3, int(min(y.sum(), len(y) - y.sum())))
    if k < 2:
        return 30.0
    folds = _folds(y, k, seed=1)
    best, best_loss = L2_GRID[0], np.inf
    for l2 in L2_GRID:
        total = 0.0
        for test in folds:
            train = np.setdiff1d(np.arange(len(y)), test)
            w, b = _fit(x[train], y[train], l2)
            p = np.clip(expit(x[test] @ w + b), 1e-6, 1 - 1e-6)
            total -= (y[test] * np.log(p) + (1 - y[test]) * np.log(1 - p)).sum()
        if total < best_loss:
            best, best_loss = l2, total
    return best


def train(embeddings: np.ndarray, labels: np.ndarray) -> tuple[dict, dict]:
    """Fit a head and estimate how it does on examples it has not seen.

    Returns (head, metrics). head holds everything predict() needs; metrics holds
    held-out accuracy and every example's held-out score, in input order.
    """
    y = labels.astype(int)
    n_pos, n_neg = int(y.sum()), int(len(y) - y.sum())
    if min(n_pos, n_neg) < MIN_PER_CLASS:
        raise ValueError(
            f"Need at least {MIN_PER_CLASS} liked and {MIN_PER_CLASS} disliked examples"
        )
    center = embeddings.mean(0)
    scale = embeddings.std(0) + 1e-6
    x = (embeddings - center) / scale
    l2 = _choose_l2(x, y)
    held = np.zeros(len(y))
    for test in [np.array([i]) for i in range(len(y))] if len(y) <= LOO_MAX else _folds(y, 10):
        train_idx = np.setdiff1d(np.arange(len(y)), test)
        w, b = _fit(x[train_idx], y[train_idx], l2)
        held[test] = expit(x[test] @ w + b)
    right = (held >= 0.5) == (y == 1)
    w, b = _fit(x, y, l2)
    head = {
        "weights": w.tolist(),
        "bias": b,
        "center": center.tolist(),
        "scale": scale.tolist(),
        "l2": l2,
    }
    metrics = {
        "liked": n_pos,
        "disliked": n_neg,
        "heldout_accuracy": float(right.mean()),
        "heldout_balanced_accuracy": float(0.5 * (right[y == 1].mean() + right[y == 0].mean())),
        "heldout_method": "leave-one-out" if len(y) <= LOO_MAX else "10-fold",
        "heldout_scores": held.round(4).tolist(),
    }
    return head, metrics


def predict(head: dict, embedding: np.ndarray) -> float:
    x = (embedding - np.asarray(head["center"])) / np.asarray(head["scale"])
    return float(expit(x @ np.asarray(head["weights"]) + head["bias"]))
