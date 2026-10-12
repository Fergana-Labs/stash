"""Distill automatic annotations and overriding human ratings into a personal model."""

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
    ratings = await pool.fetch(
        """SELECT DISTINCT ON (trace_id,step_id) trace_id,step_id,rating FROM rm_annotations
        WHERE owner_user_id=$1 AND trace_id=ANY($2::uuid[]) AND NOT label_error
        AND rating IS NOT NULL ORDER BY trace_id,step_id,updated_at DESC,created_at DESC,id DESC""",
        owner,
        trace_ids,
    )
    human = {
        (row["trace_id"], str(row["step_id"]) if row["step_id"] else None): (
            1.0 if row["rating"] > 0 else -1.0 if row["rating"] < 0 else None
        )
        for row in ratings
    }
    # Disputed targets remain excluded even if an earlier rating exists.
    disputed = await pool.fetch(
        """SELECT trace_id,step_id FROM rm_annotations WHERE owner_user_id=$1
        AND trace_id=ANY($2::uuid[]) AND label_error""",
        owner,
        trace_ids,
    )
    disputed_targets = {
        (r["trace_id"], str(r["step_id"]) if r["step_id"] else None) for r in disputed
    }
    actions: dict[UUID, dict[str, float]] = {}
    for call in calls:
        trace_id = current[call["evaluation_id"]]["trace_id"]
        if (trace_id, None) in blocked:
            continue
        answers = {r["criterion_id"]: r for r in call["result"].get("results", [])}
        for target in call["input_snapshot"].get("targets", []):
            credit = policy.expected_credit(answers.get(target["question_id"], {}))
            if credit is not None and (trace_id, target["step_id"]) not in blocked:
                actions.setdefault(trace_id, {})[target["step_id"]] = credit

    for (tid, step_id), rating in human.items():
        if (
            step_id is not None
            and rating is not None
            and (tid, None) not in disputed_targets
            and (tid, step_id) not in disputed_targets
        ):
            actions.setdefault(tid, {})[step_id] = rating

    def partition(trace_id):
        return (
            "eval"
            if config["task_groups"][str(trace_id)] in config["evaluation_groups"]
            else "train"
        )

    buckets = defaultdict(list)
    per_trace = max(2, max_pairs // max(1, len(current)))
    evaluations = {row["trace_id"]: row for row in current.values()}
    for tid, steps in steps_by_trace.items():
        evaluation = evaluations.get(tid)
        candidates = [
            (index, actions[tid][str(step["id"])])
            for index, step in enumerate(steps)
            if str(step["id"]) in actions.get(tid, {}) and policy.action(step)
        ]
        # Bound pair construction before rendering long prefixes.
        candidates = candidates[: config.get("max_actions_per_trace", 24)]
        comparisons = [(good, bad) for good in candidates for bad in candidates if good[1] > bad[1]]
        random.Random(0).shuffle(comparisons)
        for (good, chosen_credit), (bad, rejected_credit) in comparisons[:per_trace]:
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
                    "source": "human_annotation"
                    if (tid, str(steps[good]["id"])) in human
                    or (tid, str(steps[bad]["id"])) in human
                    else "automatic_annotation",
                    "credit_method": "human_rating_override"
                    if (tid, str(steps[good]["id"])) in human
                    or (tid, str(steps[bad]["id"])) in human
                    else policy.CREDIT_METHOD,
                    "chosen_credit": chosen_credit,
                    "chosen_step_index": steps[good]["idx"],
                    "rejected_step_index": steps[bad]["idx"],
                    "rejected_credit": rejected_credit,
                    "evaluation_id": str(evaluation["id"]) if evaluation else None,
                }
            )
    # Compare definite whole-trace outcomes only within the preassigned split.
    # Uncertain/partial outcomes never become invented binary labels.
    outcomes = [dict(r) for r in current.values() if (r["trace_id"], None) not in blocked]
    for (tid, step_id), rating in human.items():
        if step_id is None and rating is not None and (tid, None) not in disputed_targets:
            outcomes.append(
                {
                    "trace_id": tid,
                    "id": None,
                    "outcome": "success" if rating > 0 else "failure",
                    "human": True,
                }
            )
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
                    "source": "human_annotation"
                    if good.get("human") or bad.get("human")
                    else "automatic_annotation",
                    "evaluation_ids": [
                        str(row["id"]) for row in (good, bad) if row["id"] is not None
                    ],
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
