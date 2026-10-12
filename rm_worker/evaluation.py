"""Trace-disjoint evaluation and a stable display scale for learned action rewards."""

import math
import random
import statistics


def split_pairs(pairs: list[dict]) -> tuple[list[dict], list[dict]]:
    if len(pairs) < 2:
        raise ValueError("need at least 2 preference pairs to train a reward model")
    origins = [set(p.get("trace_ids") or [p["trace_id"]]) for p in pairs]
    traces = sorted(set().union(*origins))
    if len(traces) < 2:
        return pairs, []
    random.Random(0).shuffle(traces)
    held_out = set(traces[: max(1, round(len(traces) * 0.1))])
    train = [p for p, ids in zip(pairs, origins, strict=True) if ids.isdisjoint(held_out)]
    test = [p for p, ids in zip(pairs, origins, strict=True) if ids <= held_out]
    # Cross-partition pairs are discarded, never used to expose held-out traces in training.
    # Tiny datasets may have no usable disjoint split; report no evaluation in that case.
    if not train or (
        any(p.get("granularity") == "action" for p in pairs)
        and not any(p.get("granularity") == "action" for p in train)
    ):
        return pairs, []
    return train, test


def reward_stats(scores: list[float]) -> dict:
    if len(scores) < 2 or not all(math.isfinite(s) for s in scores):
        raise ValueError("need at least 2 finite rewards for a display scale")
    std = statistics.pstdev(scores)
    if std == 0:
        raise ValueError("every preference response got the same reward")
    return {"mean": statistics.fmean(scores), "std": std}


def preference_accuracies(pairs: list[dict], rewards: list[float]) -> dict:
    """Reuse one held-out scoring pass for all reported preference metrics."""
    if len(rewards) != 2 * len(pairs) or not all(math.isfinite(r) for r in rewards):
        raise ValueError("need two finite rewards per held-out pair")
    groups = {"eval_accuracy": [], "action_eval_accuracy": [], "tool_eval_accuracy": []}
    for i, pair in enumerate(pairs):
        correct = rewards[2 * i] > rewards[2 * i + 1]
        groups["eval_accuracy"].append(correct)
        if pair.get("granularity") == "action":
            groups["action_eval_accuracy"].append(correct)
            if pair.get("action_type") == "tool_call":
                groups["tool_eval_accuracy"].append(correct)
    return {key: sum(values) / len(values) if values else None for key, values in groups.items()}


def action_reference_rewards(pairs: list[dict], rewards: list[float]) -> list[float]:
    if len(rewards) != 2 * len(pairs):
        raise ValueError("need two calibration rewards per training pair")
    return [
        rewards[2 * i + side]
        for i, pair in enumerate(pairs)
        if pair.get("granularity") == "action"
        for side in (0, 1)
    ]


def action_score_rows(items: list[dict], scores: list[float], stats: dict) -> list[dict]:
    """Credit is a relative reward, not correctness probability or causal contribution."""
    mean, std = stats["mean"], stats["std"]
    if not math.isfinite(mean) or not math.isfinite(std) or std <= 0:
        raise ValueError("invalid action reward scale")
    rows = []
    for item, score in zip(items, scores, strict=True):
        if not math.isfinite(score):
            raise ValueError("non-finite action reward")
        rows.append(
            {
                "trace_id": item["trace_id"],
                "step_id": item["step_id"],
                "score": score,
                "credit": math.tanh((score - mean) / (2 * std)),
            }
        )
    return rows
