"""Distill current automatic annotations into an explicitly requested personal model."""

import random
from collections import defaultdict
from uuid import UUID

from rm_worker.context import render_action_input, render_trace_input

from ...database import get_pool
from . import datasets
from . import workbench_evaluation as policy


async def build_pairs(
    owner: UUID, trace_ids: list[UUID], config: dict, max_pairs: int
) -> list[dict]:
    pool = get_pool()
    steps_by_trace = await datasets._steps_by_trace(owner, trace_ids=trace_ids)
    rows = await pool.fetch(
        """SELECT DISTINCT ON (e.trace_id) e.* FROM rm_wb_evaluations e
        JOIN rm_traces t ON t.id=e.trace_id WHERE t.owner_user_id=$1 AND t.id=ANY($2::uuid[])
        AND e.policy_version=$3 AND e.model=$4 ORDER BY e.trace_id,e.created_at DESC""",
        owner,
        trace_ids,
        policy.POLICY_VERSION,
        policy.model(),
    )
    current = {
        r["id"]: r
        for r in rows
        if r["status"] == "completed"
        and r["revision_hash"] == policy.revision_hash(steps_by_trace.get(r["trace_id"], []))
    }
    calls = await pool.fetch(
        "SELECT * FROM rm_wb_evaluation_calls WHERE evaluation_id=ANY($1::uuid[]) AND status='completed' AND batch_index>0",
        list(current),
    )
    excluded = await pool.fetch(
        """SELECT trace_id,step_id FROM rm_annotations WHERE owner_user_id=$1
        AND trace_id=ANY($2::uuid[]) AND (label_error OR rating IS NOT NULL)
        UNION SELECT trace_id,coalesce(evaluation_target_step_id,target_step_id) FROM rm_wb_feedback
        WHERE owner_user_id=$1 AND trace_id=ANY($2::uuid[]) AND review_status='accepted'
        AND change_kind IN ('judge_error','both','label_only')""",
        owner,
        trace_ids,
    )
    blocked = {(r["trace_id"], str(r["step_id"]) if r["step_id"] else None) for r in excluded}
    actions: dict[UUID, dict[str, float]] = {}
    for call in calls:
        trace_id = current[call["evaluation_id"]]["trace_id"]
        if (trace_id, None) in blocked:
            continue
        answers = {r["criterion_id"]: r for r in call["result"].get("results", [])}
        for target in call["input_snapshot"].get("targets", []):
            credit = policy.credit_of(answers.get(target["question_id"], {}))
            if credit is not None and (trace_id, target["step_id"]) not in blocked:
                actions.setdefault(trace_id, {})[target["step_id"]] = credit

    def partition(trace_id):
        return (
            "eval"
            if config["task_groups"][str(trace_id)] in config["evaluation_groups"]
            else "train"
        )

    buckets = defaultdict(list)
    per_trace = max(2, max_pairs // max(1, len(current)))
    for evaluation in current.values():
        tid = evaluation["trace_id"]
        steps = steps_by_trace[tid]
        candidates = [
            (index, actions[tid][str(step["id"])])
            for index, step in enumerate(steps)
            if str(step["id"]) in actions.get(tid, {}) and policy.action(step)
        ]
        # Bound pair construction before rendering long prefixes.
        candidates = candidates[: config.get("max_actions_per_trace", 24)]
        comparisons = [(good, bad) for good in candidates for bad in candidates if good[1] > bad[1]]
        random.Random(0).shuffle(comparisons)
        for (good, _), (bad, _) in comparisons[:per_trace]:
            buckets[partition(tid), "action"].append(
                {
                    "chosen": render_action_input(steps[: good + 1], config["rubric"]),
                    "rejected": render_action_input(steps[: bad + 1], config["rubric"]),
                    "trace_id": str(tid),
                    "trace_ids": [str(tid)],
                    "granularity": "action",
                    "action_type": "tool_call"
                    if steps[good]["tool_name"] and steps[bad]["tool_name"]
                    else "response",
                    "source": "automatic_annotation",
                    "evaluation_id": str(evaluation["id"]),
                }
            )
    # Compare definite whole-trace outcomes only within the preassigned split.
    # Uncertain/partial outcomes never become invented binary labels.
    outcomes = [r for r in current.values() if (r["trace_id"], None) not in blocked]
    for good in outcomes:
        if good["outcome"] != "success":
            continue
        for bad in outcomes:
            if bad["outcome"] != "failure" or partition(good["trace_id"]) != partition(
                bad["trace_id"]
            ):
                continue
            bucket = buckets[partition(good["trace_id"]), "trace"]
            if len(bucket) >= max_pairs:
                break
            bucket.append(
                {
                    "chosen": render_trace_input(
                        steps_by_trace[good["trace_id"]], config["rubric"]
                    ),
                    "rejected": render_trace_input(
                        steps_by_trace[bad["trace_id"]], config["rubric"]
                    ),
                    "trace_id": str(good["trace_id"]),
                    "trace_ids": [str(good["trace_id"]), str(bad["trace_id"])],
                    "granularity": "trace",
                    "action_type": "response",
                    "source": "automatic_annotation",
                    "evaluation_ids": [str(good["id"]), str(bad["id"])],
                }
            )
    # Preserve both signals and the held-out split when applying the dataset cap.
    for bucket in buckets.values():
        random.Random(0).shuffle(bucket)
    pairs = []
    while len(pairs) < max_pairs and any(buckets.values()):
        for bucket in buckets.values():
            if bucket and len(pairs) < max_pairs:
                pairs.append(bucket.pop())
    return pairs


async def score_items(owner: UUID, trace_ids: list[UUID], rubric: list[str]) -> list[dict]:
    return [
        {
            "trace_id": str(tid),
            "text": render_trace_input(steps, rubric),
            "step_ids": [str(step["id"]) for step in steps],
        }
        for tid, steps in (await datasets._steps_by_trace(owner, trace_ids=trace_ids)).items()
        if steps
    ]
