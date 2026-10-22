"""The trainable part of a taste classifier: a logistic head over frozen image embeddings.

Embeddings are standardized per dimension, then fit with class-balanced L2 logistic
regression by L-BFGS. The L2 strength is chosen by cross-validated log-loss, not
accuracy: accuracy ties favor the strongest regularization, which squashes every
probability toward 0.5 and makes scores useless for ranking. Held-out metrics come
from predicting each example with a head fit without it (leave-one-out for small
sets, stratified 10-fold above that).

Disliked examples come in groups (the person's own, the build's imitations, the shared
off-style set). Each present group gets an equal share of the disliked weight, so a large
off-style set teaches "clearly not this style" without drowning out the near-misses, and
held-out results are reported per group: one accuracy over everything would be inflated
by easy off-style images.

The head also records how similar the liked examples are to each other (each one's
nearest other liked example, by cosine). An image less similar to every liked example
than that is outside what the examples cover, and predict() caps its score: a linear head
extrapolates arbitrarily far from its data, which is how a flat peach square scored 0.94.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_expit

L2_GRID = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0)
MIN_PER_CLASS = 3
LOO_MAX = 60


def _weights(y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Liked and disliked each weigh half; within disliked, each group weighs the same."""
    sw = np.zeros(len(y))
    sw[y == 1] = len(y) / (2 * max(1, int((y == 1).sum())))
    neg = sorted({g for g, label in zip(groups, y) if label == 0})
    for g in neg:
        members = (groups == g) & (y == 0)
        sw[members] = len(y) / (2 * len(neg) * members.sum())
    return sw


def _fit(
    x: np.ndarray, y: np.ndarray, l2: float, groups: np.ndarray | None = None
) -> tuple[np.ndarray, float]:
    """Group-balanced L2 logistic regression; returns (weights, bias)."""
    sw = _weights(y, groups if groups is not None else np.where(y == 1, "liked", "disliked"))
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


def _folds(
    y: np.ndarray, k: int, seed: int = 0, groups: np.ndarray | None = None
) -> list[np.ndarray]:
    """k folds stratified by group (by class when there are no groups)."""
    rng = np.random.default_rng(seed)
    strata = groups if groups is not None else y
    folds: list[list[int]] = [[] for _ in range(k)]
    for c in sorted(set(strata.tolist())):
        idx = rng.permutation(np.flatnonzero(strata == c))
        for i, j in enumerate(idx):
            folds[i % k].append(int(j))
    return [np.array(f, dtype=int) for f in folds if f]


def _choose_l2(x: np.ndarray, y: np.ndarray, groups: np.ndarray) -> float:
    k = min(3, int(min(y.sum(), len(y) - y.sum())))
    if k < 2:
        return 30.0
    folds = _folds(y, k, seed=1, groups=groups)
    sw = _weights(y, groups)
    best, best_loss = L2_GRID[0], np.inf
    for l2 in L2_GRID:
        total = 0.0
        for test in folds:
            train = np.setdiff1d(np.arange(len(y)), test)
            w, b = _fit(x[train], y[train], l2, groups[train])
            p = np.clip(expit(x[test] @ w + b), 1e-6, 1 - 1e-6)
            nll = y[test] * np.log(p) + (1 - y[test]) * np.log(1 - p)
            total -= (sw[test] * nll).sum()
        if total < best_loss:
            best, best_loss = l2, total
    return best


def _unit(a: np.ndarray) -> np.ndarray:
    return a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-12)


def train(
    embeddings: np.ndarray, labels: np.ndarray, groups: np.ndarray | None = None
) -> tuple[dict, dict]:
    """Fit a head and estimate how it does on examples it has not seen.

    groups names each row's source ("liked", "disliked", "imitation", "offstyle");
    without it every disliked row is one group. Returns (head, metrics). head holds
    everything predict() needs; metrics holds held-out accuracy overall and per group,
    and every example's held-out score, in input order.
    """
    y = labels.astype(int)
    groups = np.asarray(groups) if groups is not None else np.where(y == 1, "liked", "disliked")
    n_pos, n_neg = int(y.sum()), int(len(y) - y.sum())
    if min(n_pos, n_neg) < MIN_PER_CLASS:
        raise ValueError(
            f"Need at least {MIN_PER_CLASS} liked and {MIN_PER_CLASS} disliked examples"
        )
    center = embeddings.mean(0)
    scale = embeddings.std(0) + 1e-6
    x = (embeddings - center) / scale
    l2 = _choose_l2(x, y, groups)
    held = np.zeros(len(y))
    tests = (
        [np.array([i]) for i in range(len(y))]
        if len(y) <= LOO_MAX
        else _folds(y, 10, groups=groups)
    )
    for test in tests:
        train_idx = np.setdiff1d(np.arange(len(y)), test)
        w, b = _fit(x[train_idx], y[train_idx], l2, groups[train_idx])
        held[test] = expit(x[test] @ w + b)
    w, b = _fit(x, y, l2, groups)
    liked = _unit(embeddings[y == 1])
    sims = liked @ liked.T
    np.fill_diagonal(sims, -1)
    floor = float(sims.max(1).min())
    # Held-out results include the guard predict() applies, judging each image by its
    # nearest liked example other than itself: the score agents actually get.
    to_liked = _unit(embeddings) @ liked.T
    to_liked[np.flatnonzero(y == 1), np.arange(len(liked))] = -1
    held = held * _gate(to_liked.max(1), floor)
    right = (held >= 0.5) == (y == 1)
    head = {
        "weights": w.tolist(),
        "bias": b,
        "center": center.tolist(),
        "scale": scale.tolist(),
        "l2": l2,
        # Lowest similarity of a liked example to its nearest other liked example.
        "typical_floor": floor,
    }
    metrics = {
        "liked": n_pos,
        "disliked": n_neg,
        # Averaged over groups, so a big easy off-style set can't inflate it.
        "heldout_accuracy": float(
            np.mean([right[groups == g].mean() for g in set(groups.tolist())])
        ),
        "heldout_balanced_accuracy": float(0.5 * (right[y == 1].mean() + right[y == 0].mean())),
        "heldout_method": "leave-one-out" if len(y) <= LOO_MAX else "10-fold",
        # Share of each group judged correctly when held out: liked recognized, others rejected.
        "heldout_by_group": {
            g: float(right[groups == g].mean()) for g in sorted(set(groups.tolist()))
        },
        "heldout_scores": held.round(4).tolist(),
    }
    return head, metrics


OUTSIDE_MARGIN = 0.04


def predict(head: dict, embedding: np.ndarray, liked: np.ndarray | None = None) -> float:
    """Score an embedding. With the liked embeddings, an image less similar to all of them
    than they are to each other is scaled down to 0 over OUTSIDE_MARGIN of cosine."""
    x = (embedding - np.asarray(head["center"])) / np.asarray(head["scale"])
    p = float(expit(x @ np.asarray(head["weights"]) + head["bias"]))
    floor = head.get("typical_floor")
    if liked is None or floor is None or not len(liked):
        return p
    nearest = float((_unit(np.asarray(liked)) @ _unit(np.asarray(embedding))).max())
    return p * float(_gate(np.asarray(nearest), floor))


def _gate(nearest: np.ndarray, floor: float) -> np.ndarray:
    return np.clip((nearest - floor + OUTSIDE_MARGIN) / OUTSIDE_MARGIN, 0, 1)
