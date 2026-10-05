"""Pure release evaluation; inference predictions never become training labels."""

from collections import defaultdict

DEFAULT_POLICY = {
    "min_eval_pairs": 20,
    "min_tool_pairs": 5,
    "min_task_groups": 5,
    "min_domains": 2,
    "min_agents": 2,
    "min_unseen_domain_pairs": 5,
    "min_unseen_agent_pairs": 5,
    "min_accuracy": 0.75,
    "min_slice_accuracy": 0.6,
    "min_improvement": 0.01,
    "min_slice_pairs": 3,
}


def check_partition(pairs: list[dict]) -> tuple[list[dict], list[dict]]:
    train = [p for p in pairs if p["partition"] == "train"]
    test = [p for p in pairs if p["partition"] == "eval"]
    if len(train) < 2 or not test or len(train) + len(test) != len(pairs):
        raise ValueError(
            "Shared training needs at least two training pairs and a separate evaluation set"
        )
    if {p["task_group"] for p in train} & {p["task_group"] for p in test}:
        raise ValueError("A task group cannot occur in both training and evaluation")
    # Detect duplicated examples even when they have different provenance or reversed labels.
    train_texts = {p[k] for p in train for k in ("chosen", "rejected")}
    if train_texts & {p[k] for p in test for k in ("chosen", "rejected")}:
        raise ValueError("Training and evaluation contain duplicate examples")
    return train, test


def evaluate_release(
    pairs: list[dict],
    predictions: list[dict],
    baseline: list[dict] | None,
    policy: dict | None = None,
) -> dict:
    policy = dict(DEFAULT_POLICY if policy is None else policy)
    train, test = check_partition(pairs)
    expected = {p["example_id"] for p in test}

    def read(rows):
        if len(rows) != len(expected) or {r["example_id"] for r in rows} != expected:
            raise ValueError("Evaluation results do not match the frozen benchmark")
        if any(type(r["correct"]) is not bool for r in rows):
            raise ValueError("Invalid evaluation prediction")
        return {r["example_id"]: r["correct"] for r in rows}

    candidate = read(predictions)
    incumbent = read(baseline) if baseline is not None else None
    groups = defaultdict(list)
    for p in test:
        groups["overall"].append(p)
        groups[f"action:{p['action_type']}"].append(p)
        groups[f"domain:{p['domain']}"].append(p)
        groups[f"agent:{p['agent']}"].append(p)
    slices = {}
    for name, examples in groups.items():
        ids = [p["example_id"] for p in examples]
        slices[name] = {
            "count": len(ids),
            "accuracy": sum(candidate[i] for i in ids) / len(ids),
            "baseline_accuracy": sum(incumbent[i] for i in ids) / len(ids)
            if incumbent is not None
            else None,
        }
    counts = {
        "eval_pairs": len(test),
        "tool_pairs": sum(p["action_type"] == "tool_call" for p in test),
        "task_groups": len({p["task_group"] for p in test}),
        "domains": len({p["domain"] for p in test}),
        "agents": len({p["agent"] for p in test}),
        "unseen_domain_pairs": sum(p["domain"] not in {t["domain"] for t in train} for p in test),
        "unseen_agent_pairs": sum(p["agent"] not in {t["agent"] for t in train} for p in test),
    }
    reasons = [
        f"Need {policy['min_' + k]} {k}; got {v}"
        for k, v in counts.items()
        if v < policy["min_" + k]
    ]
    overall = slices["overall"]
    if overall["accuracy"] < policy["min_accuracy"]:
        reasons.append("Candidate accuracy is below the release threshold")
    for name, result in slices.items():
        if (
            result["count"] >= policy["min_slice_pairs"]
            and result["accuracy"] < policy["min_slice_accuracy"]
        ):
            reasons.append(f"Candidate accuracy is below the slice threshold on {name}")
    if incumbent is not None:
        if overall["accuracy"] - overall["baseline_accuracy"] < policy["min_improvement"]:
            reasons.append("Candidate does not improve on the deployed evaluator")
        for name, result in slices.items():
            if (
                result["count"] >= policy["min_slice_pairs"]
                and result["accuracy"] < result["baseline_accuracy"]
            ):
                reasons.append(f"Regression on {name}")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "counts": counts,
        "slices": slices,
        "policy": policy,
    }
