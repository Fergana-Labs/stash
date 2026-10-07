"""Pure online experiment policy. Rewards always use one pinned checkpoint.

Fixed-size randomized cohorts prevent repeatedly peeking until a candidate wins.
Intervals describe observed run means; they do not prove task equivalence or
generalization beyond this agent and workload.
"""

import hashlib
import json
import math
import re
import statistics

from rm_worker.context import render_action_input

from .datasets import render_action_context, render_steps

POLICY_VERSION = "online-prompt-v1"
MAX_ACTIONS = 64
WRAPPER = re.compile(r"<stash-optimization\b[^>]*>.*?</stash-optimization>", re.S)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def instruction(run, revision):
    return (
        f'<stash-optimization run="{run["id"]}" revision="{revision["id"]}">\n'
        "Apply these supplementary instructions to this task, subject to existing instructions "
        "and permissions. They do not authorize additional external actions.\n"
        f"{revision['content']}\n</stash-optimization>"
    )


def content_strings(content, depth=0):
    """MCP results may record a JSON string containing escaped instruction text."""
    yield content
    if depth >= 4:
        return
    try:
        value = json.loads(content)
    except (ValueError, TypeError):
        return

    def strings(item):
        if isinstance(item, str):
            yield from content_strings(item, depth + 1)
        elif isinstance(item, dict):
            for child in item.values():
                yield from strings(child)
        elif isinstance(item, list):
            for child in item:
                yield from strings(child)

    yield from strings(value)


def clean_steps(steps):
    # Withhold the candidate and MCP bookkeeping from the reward model. An
    # instruction cannot improve its own grade by changing the judge's context.
    result = []
    for step in steps:
        if "stash_optimization_" in (step.get("tool_name") or ""):
            continue
        original = step.get("content") or ""
        if any(WRAPPER.search(s) for s in list(content_strings(original))[1:]):
            continue
        content = WRAPPER.sub("", original).strip()
        if not content and not step.get("tool_name"):
            continue
        result.append({**step, "content": content})
    return result


def score_items(steps, trace_id, model, target_ids=None):
    steps = clean_steps(steps)
    targets = [
        i
        for i, s in enumerate(steps)
        if s["role"] == "assistant"
        and not (s.get("metadata") or {}).get("thinking")
        and (target_ids is None or s["id"] in target_ids)
    ]
    if len(targets) > MAX_ACTIONS:
        targets = [
            targets[round(i * (len(targets) - 1) / (MAX_ACTIONS - 1))] for i in range(MAX_ACTIONS)
        ]
    version = (model["metrics"] or {}).get("input_version", 1)
    rubric = (model["training_config"] or {}).get("rubric", [])
    return [
        {
            "trace_id": str(trace_id),
            "step_id": str(steps[i]["id"]),
            "text": render_action_input(steps[: i + 1], rubric)
            if version == 3
            else render_action_context(steps[: i + 1])
            if version == 2
            else render_steps(steps[: i + 1]),
        }
        for i in targets
    ]


def summary(values):
    if not values:
        return {"n": 0, "mean": None, "low": None, "high": None}
    mean = statistics.mean(values)
    margin = 2.58 * statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else None
    return {
        "n": len(values),
        "mean": mean,
        "low": mean - margin if margin is not None else None,
        "high": mean + margin if margin is not None else None,
    }


def difference(baseline, candidate):
    if len(baseline) < 2 or len(candidate) < 2:
        return {"mean": None, "low": None, "high": None}
    delta = statistics.mean(candidate) - statistics.mean(baseline)
    margin = 2.58 * math.sqrt(
        statistics.variance(baseline) / len(baseline)
        + statistics.variance(candidate) / len(candidate)
    )
    return {"mean": delta, "low": delta - margin, "high": delta + margin}


def compare(runs, per_arm, metric):
    arms = {arm: [r for r in runs if r["arm"] == arm] for arm in ("baseline", "candidate")}
    report = {
        "policy": POLICY_VERSION,
        "ready": False,
        "promote": False,
        "required_per_arm": per_arm,
        "arms": {},
    }
    for arm, rows in arms.items():
        report["arms"][arm] = {
            "assigned": len(rows),
            "completed": sum(r["status"] == "completed" for r in rows),
            "reward": summary([r["reward"] for r in rows if r["status"] == "completed"]),
            "business": summary([r["outcome"] for r in rows if r["outcome"] is not None]),
        }
    if any(len(rows) < per_arm for rows in arms.values()):
        report["reason"] = "Waiting for the fixed cohort of real agent runs."
        return report
    if any(r["status"] not in ("completed", "abandoned") for r in runs):
        report["reason"] = "Waiting for all assigned runs to finish scoring."
        return report
    if any(r["status"] == "abandoned" for r in runs):
        return {
            **report,
            "ready": True,
            "reason": "Incomplete run evidence; keep the current prompt.",
        }
    if any(r["outcome"] is None for r in runs):
        report["reason"] = "Waiting for measured business outcomes for every assigned run."
        return report
    reward = difference(*[[r["reward"] for r in arms[a]] for a in arms])
    sign = 1 if metric["direction"] == "higher" else -1
    business = difference(*[[sign * r["outcome"] for r in arms[a]] for a in arms])
    promote = reward["low"] > 0 and business["low"] >= -metric["regression_tolerance"]
    return {
        **report,
        "ready": True,
        "promote": promote,
        "reward_change": reward,
        "business_change": business,
        "reason": "Reward improved and the business guardrail passed."
        if promote
        else "The candidate did not establish reward improvement within the business guardrail.",
    }
