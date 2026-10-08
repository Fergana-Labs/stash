"""Rule-based scores for labeled steps, with credit assignment.

Each step's label has fixed points (work costs a little, an answer is worth a
lot and depends on how the user reacted). One quality check per step, answered
by a grading model, moves those points within a narrow band. When the user
reacts to an answer, part of its points is passed back to the steps that led
to it. Every number can be traced to a label, a check, or a named answer, which
is what the trace view shows. This is separate from the automatic annotation's
learned credit and never replaces it.

Everything here is a pure function over labels. The numbers and wording are
the rubric; change them here.
"""

from __future__ import annotations

# Process costs: small penalties for doing work.
COST_TOOL_READ = -0.03
COST_TOOL_SIDE_EFFECT = -0.05
COST_TOOL_ERROR_EXTRA = -0.10
COST_DUPLICATE_EXTRA = -0.10
COST_CLARIFYING = -0.05

# Outcome scores for an answer: verdict -> (asserted, hedged).
ANSWER = {
    "confirmed": (1.0, 0.8),
    "implicit_positive": (0.6, 0.5),
    "none": (0.3, 0.3),
    "partial": (0.2, 0.2),
    "rejected": (-1.0, -0.6),
}
NOT_FOUND, ERROR, HANDOFF = -0.2, -0.5, -0.1
PROPAGATING_VERDICTS = {"confirmed", "rejected", "partial", "implicit_positive"}

# Quality checks: rubric id -> (question, ordered levels as (situation, short name, value)).
# For "tool" the value is added to the label's cost (capped at 0); for the
# others it stands in for the label's flat points. An unconfirmed answer tops
# out below any answer the user accepted, and an honest "not found" stays above
# a rejected answer.
CHECKS: dict[str, tuple[str, list[tuple[str, str, float]]]] = {
    "tool": (
        "STEP_TO_JUDGE is a tool call the agent made. How was what it returned used in the steps after it in CONVERSATION?",
        [
            (
                "The same tool was called earlier with the same arguments, and this call returns the same thing again.",
                "the same call had already been made",
                -0.05,
            ),
            (
                "The call fails or returns nothing useful, and the agent's next steps carry on as if it had never happened.",
                "it failed and the agent carried on regardless",
                -0.05,
            ),
            (
                "The call returns information, and the later steps and the response to the user leave that information unused.",
                "its result was never used",
                -0.03,
            ),
            (
                "The call fails or returns nothing useful, and the agent's next steps change approach because of it: a different tool, different arguments, or a question to the user.",
                "it failed, and the agent changed approach",
                0.0,
            ),
            (
                "The call returns information that a later step or the response to the user relies on.",
                "its result was used later",
                0.03,
            ),
        ],
    ),
    "clarifying_question": (
        "STEP_TO_JUDGE is a question the agent asked the user. How does the question relate to what was already known and to what happened next in CONVERSATION?",
        [
            (
                "The user had already given this information earlier in the conversation, or an earlier tool result already showed it.",
                "the user had already said this",
                -0.15,
            ),
            (
                "The question asks for new information, and the user's reply goes unused in the steps that follow.",
                "the user's reply was never used",
                -0.08,
            ),
            (
                "The question asks for new information, and the conversation ends before the user replies.",
                "the user never replied",
                -0.05,
            ),
            (
                "The question asks for new information, and the user's reply is used in the steps that follow.",
                "the user's reply was used",
                -0.02,
            ),
        ],
    ),
    "answer_unconfirmed": (
        "STEP_TO_JUDGE is the agent's response to the user's request, and the user never reacted to it. How does what it states relate to the tool results earlier in CONVERSATION? Judge only whether the tool results contain it; whether it is true in the real world is outside this question.",
        [
            (
                "The response states a specific answer that appears in none of the earlier tool results.",
                "the answer is not in any tool result",
                0.10,
            ),
            (
                "The response states a specific answer that appears in one tool result while another tool result disagrees with it, and the response leaves that disagreement unmentioned.",
                "tool results disagree and the answer doesn't say so",
                0.15,
            ),
            (
                "The response states a specific answer that appears in the earlier tool results.",
                "the answer matches the tool results",
                0.30,
            ),
            (
                "The response states a specific answer that appears in the earlier tool results, and it tells the user what was checked and what remains unverified.",
                "it matches the tool results and says what is unverified",
                0.40,
            ),
        ],
    ),
    "not_found_unconfirmed": (
        "STEP_TO_JUDGE tells the user the requested thing could not be found, and the user never reacted to it. What search does CONVERSATION show before it?",
        [
            (
                "The response says it could not be found, and the conversation shows no search for it beforehand.",
                "no search was done first",
                -0.35,
            ),
            (
                "The response says it could not be found after a single search attempt.",
                "only one search was done",
                -0.25,
            ),
            (
                "The response says it could not be found after several different searches or sources came back empty.",
                "several searches came up empty",
                -0.15,
            ),
            (
                "The response says it could not be found after several different searches came back empty, and it tells the user what was searched and what they could provide next.",
                "several searches came up empty, and it says what to try next",
                -0.10,
            ),
        ],
    ),
}

VERDICT_WORDS = {
    "confirmed": "the user confirmed it",
    "implicit_positive": "the user accepted it and moved on",
    "partial": "the user said it was partly right",
    "rejected": "the user rejected it",
    "none": "the user never reacted",
}
OUTCOME_WORDS = {
    "answer": "Gave an answer",
    "partial_answer": "Answered only part of the request",
    "not_found": "Said it could not find it",
    "error": "Reported a failure",
    "handoff": "Handed off or declined",
}


def clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def coverage_fraction(coverage: str | None) -> float:
    try:
        done, asked = (float(x) for x in (coverage or "").split("/"))
    except ValueError:
        return 0.5
    return max(0.0, min(1.0, done / asked)) if asked > 0 else 0.5


def outcome_score(
    outcome: str | None, stance: str | None, verdict: str | None, coverage: str | None
) -> float:
    if outcome == "not_found":
        return NOT_FOUND
    if outcome == "error":
        return ERROR
    if outcome == "handoff":
        return HANDOFF
    asserted, hedged = ANSWER.get(verdict or "none", ANSWER["none"])
    base = hedged if stance == "hedged" else asserted
    if outcome == "partial_answer":
        c = coverage_fraction(coverage)
        return c * base + (1 - c) * NOT_FOUND
    return base


def process_cost(label: dict) -> float:
    if label["type"] == "clarifying_question":
        return COST_CLARIFYING
    if label["type"] != "tool_call":
        return 0.0
    cost = COST_TOOL_SIDE_EFFECT if label["effect"] == "side_effect" else COST_TOOL_READ
    if label["result"] == "error":
        cost += COST_TOOL_ERROR_EXTRA
    if label.get("duplicate_of"):
        cost += COST_DUPLICATE_EXTRA
    return cost


def base_parts(label: dict, verdict: str | None) -> list[dict]:
    """The rubric's lookup for this label, as readable line items."""
    parts = []
    if label["type"] == "tool_call":
        if label["effect"] == "side_effect":
            parts.append(
                {
                    "text": "Standard cost of an action that changes or records something",
                    "value": COST_TOOL_SIDE_EFFECT,
                }
            )
        else:
            parts.append({"text": "Standard cost of a lookup", "value": COST_TOOL_READ})
        if label["result"] == "error":
            parts.append(
                {"text": "Penalty because it returned an error", "value": COST_TOOL_ERROR_EXTRA}
            )
        if label.get("duplicate_of"):
            parts.append(
                {
                    "text": "Penalty because it repeats an earlier call",
                    "value": COST_DUPLICATE_EXTRA,
                }
            )
    elif label["type"] == "clarifying_question":
        parts.append(
            {"text": "Standard cost of asking the user a question", "value": COST_CLARIFYING}
        )
    elif label["type"] == "status_update":
        parts.append({"text": "Progress update (free)", "value": 0.0})
    if label["is_output"]:
        v = verdict or "none"
        stance = ""
        if label["outcome"] in ("answer", "partial_answer") and label["stance"]:
            stance = " with caveats" if label["stance"] == "hedged" else " without caveats"
        coverage = ""
        if label["outcome"] == "partial_answer" and label["coverage"] and "/" in label["coverage"]:
            done, asked = label["coverage"].split("/", 1)
            coverage = f" ({done} of {asked} items)"
        parts.append(
            {
                "text": f"{OUTCOME_WORDS.get(label['outcome'] or 'answer', 'Gave an answer')}{stance}{coverage}, and {VERDICT_WORDS.get(v, v)}",
                "value": round(
                    outcome_score(label["outcome"], label["stance"], v, label["coverage"]), 4
                ),
            }
        )
    return parts


def check_for(label: dict, verdict: str | None) -> str | None:
    """Which quality check applies to a labeled agent step, if any. Where the
    rubric already has ground truth (the user reacted) or nothing to grade
    (error, handoff, status update), its number is final."""
    if label["is_output"]:
        if (verdict or "none") != "none":
            return None
        if label["outcome"] in ("answer", "partial_answer"):
            return "answer_unconfirmed"
        return "not_found_unconfirmed" if label["outcome"] == "not_found" else None
    if label["type"] == "tool_call":
        return "tool"
    return "clarifying_question" if label["type"] == "clarifying_question" else None


def score_step(label: dict, verdict: str | None, check: dict | None) -> dict:
    """One agent step's cost and outcome. `check` is the grading model's answer
    to this step's quality check: {"rubric", "probabilities": {level: p}}. The
    probability-weighted value is applied, so an unsure pick moves less."""
    cost = process_cost(label)
    outcome = None
    if label["is_output"]:
        verdict = verdict or "none"
        outcome = outcome_score(label["outcome"], label["stance"], verdict, label["coverage"])
    base = clamp(cost + (outcome or 0.0))
    graded = None
    if check is not None:
        levels = CHECKS[check["rubric"]][1]
        graded = sum(
            check["probabilities"].get(i, 0.0) * value for i, (_, _, value) in enumerate(levels)
        )
        if check["rubric"] == "tool":
            cost = min(0.0, cost + graded)
        elif check["rubric"] == "clarifying_question":
            cost = graded
        elif label["outcome"] == "partial_answer":
            c = coverage_fraction(label["coverage"])
            outcome = c * graded + (1 - c) * NOT_FOUND
        else:
            outcome = graded
    return {
        "cost": cost,
        "outcome": outcome,
        "verdict": verdict if label["is_output"] else None,
        "base": base,
        "graded": graded,
    }


def score_trace(agent_steps: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    """Credit assignment and task scores.

    agent_steps: agent chunks in order, each {chunk_id, task_id, label, verdict, check}.
    Returns ({chunk_id: reward}, [task score]). When the user reacts to an
    answer, 0.3 x its outcome x 0.8^k is passed back to the step k places
    before it in the task. Passed-back credit is not part of the task score.
    """
    rows = []
    for step in agent_steps:
        scored = score_step(step["label"], step["verdict"], step["check"])
        rows.append(
            {
                **step,
                **scored,
                "score": clamp(scored["cost"] + (scored["outcome"] or 0.0)),
                "shared": [],
            }
        )

    tasks: dict[str, list[dict]] = {}
    for row in rows:
        tasks.setdefault(row["task_id"], []).append(row)
    episodes = []
    for task_id, task_rows in tasks.items():
        outputs = [i for i, r in enumerate(task_rows) if r["outcome"] is not None]
        for i in outputs:
            answer = task_rows[i]
            if answer["verdict"] in PROPAGATING_VERDICTS:
                for k, j in enumerate(range(i - 1, -1, -1), start=1):
                    task_rows[j]["shared"].append(
                        {
                            "from": answer["chunk_id"],
                            "verdict": answer["verdict"],
                            "value": round(0.3 * answer["outcome"] * 0.8**k, 4),
                        }
                    )
        costs = sum(r["cost"] for r in task_rows)
        base_costs = sum(process_cost(r["label"]) for r in task_rows)
        final = task_rows[outputs[-1]] if outputs else None
        base_final = (
            outcome_score(
                final["label"]["outcome"],
                final["label"]["stance"],
                final["verdict"],
                final["label"]["coverage"],
            )
            if final
            else 0.0
        )
        episodes.append(
            {
                "task": task_id,
                "score": round(clamp((final["outcome"] if final else 0.0) + costs), 4),
                "rubric_b_only": round(clamp(base_final + base_costs), 4),
                "answer": round(final["outcome"], 4) if final else None,
                "costs": round(costs, 4),
                "has_answer": final is not None,
            }
        )

    rewards = {}
    for row in rows:
        shared_total = sum(s["value"] for s in row["shared"])
        check = None
        if row["check"] is not None:
            question, levels = CHECKS[row["check"]["rubric"]]
            probabilities = row["check"]["probabilities"]
            level = max(range(len(levels)), key=lambda i: probabilities.get(i, 0.0))
            check = {
                "rubric": row["check"]["rubric"],
                "grader": row["check"]["grader"],
                "question": question,
                "level": level,
                "text": levels[level][0],
                "short": levels[level][1],
                "value": round(row["graded"], 4),
                "probability": probabilities.get(level),
                "mode": "adjust" if row["check"]["rubric"] == "tool" else "replace",
            }
        rewards[row["chunk_id"]] = {
            "base": round(row["base"], 4),
            "base_parts": base_parts(row["label"], row["verdict"]),
            "jev": check,
            "score": round(row["score"], 4),
            "shared": row["shared"],
            "shared_total": round(shared_total, 4),
            "total": round(clamp(row["score"] + shared_total), 4),
            "is_answer": bool(row["label"]["is_output"]),
        }
    return rewards, episodes


def summarize(labels: list[dict], episodes: list[dict]) -> dict:
    """Trace-level roll-up for the trace list."""
    return {
        "score": round(sum(e["score"] for e in episodes) / len(episodes), 4) if episodes else None,
        "episodes": episodes,
        "signals": {
            "rejections": sum(label["verdict"] == "rejected" for label in labels),
            "confirmations": sum(
                label["verdict"] in ("confirmed", "implicit_positive") for label in labels
            ),
            "tool_errors": sum(label["result"] == "error" for label in labels),
            "answers": sum(bool(label["is_output"]) for label in labels),
        },
    }
