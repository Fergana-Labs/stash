"""Information-retrieval metrics: NDCG, MRR, Precision@k, Recall@k."""

from __future__ import annotations

import math
from typing import Sequence


def dcg(grades: Sequence[float], k: int | None = None) -> float:
    """Discounted Cumulative Gain."""
    g = list(grades)[:k] if k else list(grades)
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(g))


def ndcg(grades: Sequence[float], ideal_grades: Sequence[float], k: int | None = None) -> float:
    """Normalised DCG@k.  Returns 0 when ideal DCG is 0."""
    idcg = dcg(sorted(ideal_grades, reverse=True), k)
    if idcg == 0:
        return 0.0
    return dcg(grades, k) / idcg


def precision_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of top-k retrieved items that are relevant."""
    top = list(retrieved)[:k]
    if not top:
        return 0.0
    return sum(1 for r in top if r in relevant) / k


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of relevant items that appear in top-k retrieved."""
    if not relevant:
        return 1.0
    top = list(retrieved)[:k]
    return sum(1 for r in top if r in relevant) / len(relevant)


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    """Reciprocal rank of the first relevant item (0 if none found)."""
    for i, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def mean_reciprocal_rank(queries: list[tuple[Sequence[str], set[str]]]) -> float:
    """MRR over multiple queries."""
    if not queries:
        return 0.0
    return sum(reciprocal_rank(ret, rel) for ret, rel in queries) / len(queries)


def f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def compute_retrieval_metrics(
    retrieved_names: list[str],
    scenario_relevant: list[dict],  # [{"name": str, "grade": int}]
    k_values: tuple[int, ...] = (1, 3, 5),
) -> dict[str, float]:
    """
    Compute a full suite of retrieval metrics for a single scenario.

    Args:
        retrieved_names: Ordered list of page names returned by the system.
        scenario_relevant: Ground-truth list from the scenario dataset.
        k_values: Values of k to compute P@k and R@k for.

    Returns:
        Dict of metric_name → value.
    """
    # Build graded relevance map
    grade_map: dict[str, int] = {e["name"]: e["grade"] for e in scenario_relevant}
    relevant_set = {name for name, g in grade_map.items() if g >= 2}

    # Build grade sequence in retrieval order
    retrieved_grades = [grade_map.get(name, 0) for name in retrieved_names]
    ideal_grades = sorted(grade_map.values(), reverse=True)

    metrics: dict[str, float] = {}

    for k in k_values:
        metrics[f"P@{k}"] = precision_at_k(retrieved_names, relevant_set, k)
        metrics[f"R@{k}"] = recall_at_k(retrieved_names, relevant_set, k)
        metrics[f"NDCG@{k}"] = ndcg(retrieved_grades, ideal_grades, k)

    metrics["RR"] = reciprocal_rank(retrieved_names, relevant_set)
    metrics["num_retrieved"] = float(len(retrieved_names))
    metrics["num_relevant"] = float(len(relevant_set))

    return metrics
