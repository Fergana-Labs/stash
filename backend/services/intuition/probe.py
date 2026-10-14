"""Embedding probe: a closed-form ridge readout over item embeddings.

The probe is the "what do the labeled examples look like" signal that the
rubric cannot express in words. It is a linear probe on frozen embeddings,
solved in the dual exactly like the analytical reward compiler's repair step
(c = (K + lambda I)^-1 Y, W = X^T c), so a refit on a few dozen examples takes
milliseconds and needs no GPU.

It enters the model as one more rubric question (type `probe`), so the
logistic head stacked on top learns how much to trust it next to the Jev
answers, and every explanation shows it as a driver like any criterion.

Stacking without leakage. A probe fitted on an item has memorized that item's
label; feeding that answer to the head would teach the head to over-trust the
probe. Ridge has an exact leave-one-out shortcut, (y_hat - h_ii y) / (1 - h_ii),
so every training item's stored answer is the prediction of the probe fitted
without it. Any other item (held-out, production) gets the full probe.

Multimodal items are embedded through their extracted content: an image item
carries Claude's visual description (builder.read_input), which is what the
probe reads; the raw pixels never reach the text embedder.
"""

from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from uuid import UUID

import numpy as np
from scipy.optimize import minimize_scalar

from ...database import get_pool
from .. import embeddings
from . import providers
from .spec import issues_of

MIN_ROWS = 4
RIDGES = (0.03, 0.1, 0.3, 1.0, 3.0)
PROBE_ID = "embedding_probe"
_CACHE_SIZE = 4096
_cache: OrderedDict[str, np.ndarray] = OrderedDict()


class ProbeUnavailable(ValueError):
    """The probe cannot be fitted or served (no embedder, too little data)."""


def item_text(item) -> str:
    visible = providers.judge_item(item)
    return visible if isinstance(visible, str) else providers._json(visible)


def item_hash(item) -> str:
    return hashlib.sha256(item_text(item).encode()).hexdigest()


def _embedder_name() -> str:
    embedder = embeddings.get_embedder()
    return f"{embedder.name}:{getattr(embedder, 'model', '') or ''}:{embedder.dims}"


async def embed(items: list) -> np.ndarray:
    """Unit-normalized embeddings, cached in-process by content."""
    if not embeddings.is_configured():
        raise ProbeUnavailable("No embedding provider is configured on the server")
    name = _embedder_name()
    keys = [f"{name}:{item_hash(i)}" for i in items]
    missing = [(k, item_text(i)) for k, i in zip(keys, items) if k not in _cache]
    if missing:
        unique = dict(missing)
        vectors = await embeddings.embed_batch(list(unique.values()))
        if vectors is None or any(v is None for v in vectors):
            raise ProbeUnavailable("The embedding provider failed; try again shortly")
        for key, vector in zip(unique, vectors):
            v = np.asarray(vector, dtype=float)
            _cache[key] = v / (np.linalg.norm(v) or 1.0)
            if len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)
    for k in keys:
        _cache.move_to_end(k)
    return np.stack([_cache[k] for k in keys])


# ── Math (pure numpy; unit-tested without a database) ───────────────────


def targets(output_type: str, classes: list[str], labels: list[str]) -> np.ndarray:
    """Centered one-hot for choice; +-1 per issue for multi; +-1 (good/bad) for preference."""
    if output_type == "multi":
        return np.asarray([[1.0 if c in issues_of(label) else -1.0 for c in classes] for label in labels])
    if output_type == "choice":
        index = {c: i for i, c in enumerate(classes)}
        y = np.zeros((len(labels), len(classes)))
        y[np.arange(len(labels)), [index[label] for label in labels]] = 1.0
        return y - 1.0 / len(classes)
    return np.asarray([[1.0 if label == "good" else -1.0] for label in labels])


def probabilities(output_type: str, scores: np.ndarray, scale: float) -> np.ndarray:
    z = np.atleast_2d(scores) * scale
    if output_type == "multi":
        return 1 / (1 + np.exp(-z))  # independent P(issue) per column
    if output_type == "choice":
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)
    p = 1 / (1 + np.exp(-z[:, 0]))
    return np.stack([p, 1 - p], axis=1)  # [good, bad]


def _nll(output_type: str, scores: np.ndarray, y: np.ndarray, scale: float) -> float:
    p = probabilities(output_type, scores, scale)
    if output_type == "multi":
        p_true = np.where(y > 0, p, 1 - p)
        return float(-np.mean(np.log(np.clip(p_true, 1e-9, 1))))
    if output_type == "choice":
        truth = y.argmax(axis=1)
    else:
        truth = np.where(y[:, 0] > 0, 0, 1)
    return float(-np.mean(np.log(np.clip(p[np.arange(len(truth)), truth], 1e-9, 1))))


def _fit_scale(output_type: str, scores: np.ndarray, y: np.ndarray) -> float:
    result = minimize_scalar(
        lambda log_s: _nll(output_type, scores, y, math.exp(log_s)),
        bounds=(math.log(0.1), math.log(200)),
        method="bounded",
    )
    return math.exp(result.x)


def solve(output_type: str, X: np.ndarray, y: np.ndarray) -> dict:
    """Pick the ridge by exact leave-one-out log loss; return weights and LOO scores."""
    K = X @ X.T
    n = len(X)
    best = None
    for ridge in RIDGES:
        inv = np.linalg.inv(K + ridge * np.eye(n))
        H = K @ inv
        fitted = H @ y
        h = np.clip(np.diag(H), 0, 0.999)[:, None]
        loo = (fitted - h * y) / (1 - h)
        scale = _fit_scale(output_type, loo, y)
        loss = _nll(output_type, loo, y, scale)
        if best is None or loss < best["loo_log_loss"]:
            best = {
                "ridge": ridge,
                "weights": X.T @ (inv @ y),  # d x k
                "loo_scores": loo,
                "scale": scale,
                "loo_log_loss": loss,
            }
    probs = probabilities(output_type, best["loo_scores"], best["scale"])
    if output_type == "multi":
        best["loo_accuracy"] = float(np.mean(np.all((probs >= 0.5) == (y > 0), axis=1)))
        return best
    truth = y.argmax(axis=1) if output_type == "choice" else np.where(y[:, 0] > 0, 0, 1)
    best["loo_accuracy"] = float(np.mean(probs.argmax(axis=1) == truth))
    return best


def options(output_type: str, classes: list[str]) -> list[str]:
    return list(classes) if output_type in ("choice", "multi") else ["good", "bad"]


# ── Fit and serve ────────────────────────────────────────────────────────


def training_items(output_type: str, examples: list[dict]) -> tuple[list, list[str]]:
    """Labeled training items; a preference pair contributes its winner as good, loser as bad."""
    items, labels = [], []
    for e in examples:
        if e["label"] is None or e["needs_review"] or e["split"] != "train":
            continue
        if e["kind"] == "pair":
            winner, loser = (e["item"], e["item_b"]) if e["label"] == "a" else (e["item_b"], e["item"])
            items += [winner, loser]
            labels += ["good", "bad"]
        else:
            items.append(e["item"])
            labels.append(e["label"])
    return items, labels


async def fit(model_id: UUID, output_type: str, classes: list[str], examples: list[dict]) -> dict:
    """Fit and store a probe on the model's labeled training examples."""
    items, labels = training_items(output_type, examples)
    if len(items) < MIN_ROWS or (len(set(labels)) < 2 and output_type != "multi"):
        raise ProbeUnavailable(
            f"The probe needs at least {MIN_ROWS} labeled training examples of two kinds"
        )
    X = await embed(items)
    y = targets(output_type, classes, labels)
    solved = solve(output_type, X, y)
    probs = probabilities(output_type, solved["loo_scores"], solved["scale"])
    opts = options(output_type, classes)
    loo: dict[str, list[list[float]]] = {}
    for item, row in zip(items, probs):
        loo.setdefault(item_hash(item), []).append([float(p) for p in row])
    loo_answers = {
        key: dict(zip(opts, np.mean(rows, axis=0).round(6).tolist())) for key, rows in loo.items()
    }
    metrics = {
        "rows": len(items),
        "ridge": solved["ridge"],
        "loo_accuracy": solved["loo_accuracy"],
        "loo_log_loss": solved["loo_log_loss"],
        "output_type": output_type,
    }
    row = await get_pool().fetchrow(
        """INSERT INTO intuition_probes (model_id, embedder, dims, classes, weights, scale, loo, metrics)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id, created_at""",
        model_id,
        _embedder_name(),
        int(X.shape[1]),
        opts,
        np.round(solved["weights"], 6).tolist(),
        float(solved["scale"]),
        loo_answers,
        metrics,
    )
    return {"id": str(row["id"]), "options": opts, "metrics": metrics}


def question(probe: dict, output_type: str, labels: list[dict]) -> dict:
    described = {label["id"]: label.get("description") or label["id"] for label in labels}
    if output_type == "multi":
        criteria = {o: f"Resembles your examples with {described.get(o, o)}" for o in probe["options"]}
    elif output_type == "choice":
        criteria = {o: f"Resembles your examples labeled {described.get(o, o)}" for o in probe["options"]}
    else:
        criteria = {"good": "Resembles the outputs you preferred", "bad": "Resembles the outputs you rejected"}
    return {
        "id": PROBE_ID,
        "type": "probe",
        "prompt": "Learned from your labeled examples: which of them does this item most resemble?",
        "criteria": criteria,
        "version_id": probe["id"],
    }


async def answer(version: dict, question: dict, item) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM intuition_probes WHERE id = $1 AND model_id = $2",
        UUID(question["version_id"]),
        version["model_id"],
    )
    if row is None:
        raise providers.ProviderError(f"The probe used by question {question['id']} was not found")
    stored = row["loo"].get(item_hash(item))
    if stored is not None:
        probs = stored
    else:
        if row["embedder"] != _embedder_name():
            raise providers.ProviderError(
                "The embedding provider changed since this probe was fitted; retrain the model"
            )
        try:
            (x,) = await embed([item])
        except ProbeUnavailable as exc:
            raise providers.ProviderError(str(exc), retryable=True) from exc
        weights = np.asarray(row["weights"])
        # Preference probes have one score column (good vs bad); choice and multi one per class.
        output_type = row["metrics"].get("output_type") or ("preference" if weights.shape[1] == 1 else "choice")
        scores = x @ weights
        p = probabilities(output_type, scores[None, :], row["scale"])[0]
        probs = dict(zip(row["classes"], p.tolist()))
    if (row["metrics"] or {}).get("output_type") == "multi":
        # Independent per-issue probabilities: they do not sum to 1.
        return {"type": "probe", "probabilities": {o: float(probs[o]) for o in question["criteria"]}}
    return providers._checked({o: float(probs[o]) for o in question["criteria"]}, question)
