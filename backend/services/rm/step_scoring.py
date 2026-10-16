"""Rule-based scores for labeled steps, with credit assignment.

Each step's label has fixed points from the tables below: work costs a little,
an answer the user reacted to is worth what the reaction says, and an answer
nobody reacted to is worth what the grounding of its key claim says. Whatever
the labels leave open is one multiple-choice question per step for the grading
model (Jev), and the step's points are the probability-weighted average of the
options' points. When the user reacts to an answer, 30% of its points is split
among the steps that caused it, so credit is moved, never created. Every
number can be traced to a label, a question, or a named answer, which is what
the trace view shows.

Everything here is a pure function over labels. The numbers and wording are
the rubric; change them here, and keep the orderings `test_step_labeling`
pins: guessing never pays, honesty beats being wrong, users outrank both
models, hedging only pays when warranted, work only breaks ties, credit is
conserved.
"""

from __future__ import annotations

# Work costs points: small penalties that flag wasteful steps and break ties.
COST_TOOL_READ = -0.03
COST_TOOL_SIDE_EFFECT = -0.05
COST_CLARIFYING = -0.05
COST_TOOL_ERROR_EXTRA = -0.10
COST_DUPLICATE_EXTRA = -0.10
COST_ARGS_MISMATCH_EXTRA = -0.10
COST_UNAPPROVED_EXTRA = -0.20
TASK_COST_CAP = -0.10

# Answers the user reacted to: verdict -> (asserted, hedged).
ANSWER = {
    "confirmed": (1.0, 0.8),
    "implicit_positive": (0.6, 0.5),
    "partial": (0.2, 0.2),
    "rejected": (-1.0, -0.6),
}
# Answers nobody reacted to, by the grounding of the key claim: (asserted, hedged).
GROUNDING = {
    "supported": (0.30, 0.35),
    "no_lookup_needed": (0.30, 0.30),
    "partly_supported": (0.10, 0.10),
    "no_source": (-0.40, -0.30),
    "contradicts_tool": (-0.50, -0.40),
}
# "Not found", by the lookups earlier in the task.
NOT_FOUND = {"none": -0.35, "one": -0.25, "several": -0.15, "several_next": -0.10}
ERROR, HANDOFF = -0.5, -0.1
REACTIONS = {"confirmed", "implicit_positive", "partial", "rejected"}
ANSWER_OUTCOMES = ("answer", "partial_answer", "handoff")
KEEP = 0.7  # an answer the user reacted to keeps this much; the rest is shared
EARLIER_PENALTY = {"rejected": -0.25, "partial": -0.10}

# Without the grading model, an unclear label falls back to these.
FALLBACK = {
    "verdict": "none",
    "grounding": "partly_supported",
    "args_match": "match",
    "approved": "yes",
}

# Jev's questions about a step: rubric id -> (question, levels as (situation, short name, points)).
# For "tool" the points are added to the label's cost (capped at 0); for
# "clarifying_question" they stand in for the flat cost.
CHECKS: dict[str, tuple[str, list[tuple[str, str, float]]]] = {
    "tool": (
        "STEP_TO_JUDGE is a tool call the agent made. What happened with its result in the steps after it in CONVERSATION?",
        [
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
        "STEP_TO_JUDGE is a question the agent asked the user. Was it worth asking, given what was already known and what happened next in CONVERSATION?",
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
}

# Jev's questions for a label marked "unclear": field -> (question, levels as
# (situation, short name, label value)). The points follow the tables above.
LABEL_CHECKS: dict[str, tuple[str, list[tuple[str, str, str]]]] = {
    "verdict": (
        "STEP_TO_JUDGE is the user's message after the agent's response. How does it react to that response?",
        [
            (
                "The user says the response is right, or acts on it.",
                "the user confirmed it",
                "confirmed",
            ),
            (
                "The user thanks the agent or moves on to another request without disputing the response.",
                "the user accepted it and moved on",
                "implicit_positive",
            ),
            (
                "The user says some of the response is right and some is wrong.",
                "the user said it was partly right",
                "partial",
            ),
            (
                "The user says the response is wrong, corrects it, or asks for the same thing again.",
                "the user rejected it",
                "rejected",
            ),
            (
                "The message does not refer to the response at all.",
                "the user did not react to it",
                "none",
            ),
        ],
    ),  # fmt: skip
    "grounding": (
        "STEP_TO_JUDGE is the agent's response to the user. Its key claim is the date, amount, id, status or policy fact the user asked for. How does that key claim relate to the tool results earlier in CONVERSATION? Sums, counts, comparisons and paraphrases of a tool result count as stated in it. Judge only whether the tool results contain it, not whether it is true.",
        [
            (
                "The key claim is stated in or derived from the tool results.",
                "the key claim is in the tool results",
                "supported",
            ),
            ("The request needed no lookup.", "no lookup was needed", "no_lookup_needed"),
            (
                "Some of the key claim is in the tool results and some is not.",
                "the key claim is partly in the tool results",
                "partly_supported",
            ),
            (
                "The key claim appears in no tool result.",
                "the key claim has no source",
                "no_source",
            ),
            (
                "A tool result says something different from the key claim.",
                "the key claim contradicts a tool result",
                "contradicts_tool",
            ),
        ],
    ),  # fmt: skip
    "args_match": (
        "STEP_TO_JUDGE is a tool call the agent made. Do its arguments match what the user asked for in CONVERSATION?",
        [
            (
                "The arguments fit what the user asked for.",
                "its arguments match the request",
                "match",
            ),
            (
                "The arguments name a different item, id, date, filter or target than the user asked for.",
                "its arguments don't match the request",
                "mismatch",
            ),
        ],
    ),  # fmt: skip
    "approved": (
        "STEP_TO_JUDGE is a tool call that changes or records something. Had the user asked for or approved this change earlier in the task in CONVERSATION?",
        [
            (
                "The user asked for or approved this change earlier in the task.",
                "the user had approved it",
                "yes",
            ),
            (
                "Nothing earlier in the task shows the user asking for or approving it.",
                "the user had not approved it",
                "no",
            ),
        ],
    ),  # fmt: skip
}

VERDICT_WORDS = {
    "confirmed": "the user confirmed it",
    "implicit_positive": "the user accepted it and moved on",
    "partial": "the user said it was partly right",
    "rejected": "the user rejected it",
    "none": "the user never reacted",
}
GROUNDING_WORDS = {
    "supported": "its key claim is in the tool results",
    "no_lookup_needed": "it needed no lookup",
    "partly_supported": "its key claim is only partly in the tool results",
    "no_source": "its key claim has no source",
    "contradicts_tool": "its key claim contradicts a tool result",
}
NOT_FOUND_WORDS = {
    "none": "with no lookup first",
    "one": "after one lookup",
    "several": "after several lookups",
    "several_next": "after several lookups, saying what to try next",
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


def check_question(rubric: str) -> tuple[str, list[str]]:
    """The question and option texts for a step check or an unclear label."""
    question, levels = CHECKS.get(rubric) or LABEL_CHECKS[rubric]
    return question, [level[0] for level in levels]


def resolved(field: str, value: str | None, checks: dict) -> dict[str, float]:
    """A label's value as a distribution: certain unless it was unclear, then
    Jev's probabilities over the options, or the fallback without Jev."""
    if value != "unclear":
        return {value: 1.0}
    answer = checks.get(field)
    if answer is None:
        return {FALLBACK[field]: 1.0}
    levels = LABEL_CHECKS[field][1]
    dist: dict[str, float] = {}
    for i, (_, _, option) in enumerate(levels):
        dist[option] = dist.get(option, 0.0) + answer["probabilities"].get(i, 0.0)
    total = sum(dist.values())
    return {k: v / total for k, v in dist.items()} if total > 0 else {FALLBACK[field]: 1.0}


def likeliest(dist: dict[str, float]) -> str:
    return max(dist, key=dist.get)


def not_found_tier(lookups: int, next_steps: bool | None) -> str:
    if lookups == 0:
        return "none"
    if lookups == 1:
        return "one"
    return "several_next" if next_steps else "several"


def answer_points(
    label: dict, verdict: str, grounding: str, not_found: float, verdict_coverage: str | None
) -> float:
    """An output's points for one verdict and one grounding value."""
    outcome = label["outcome"]
    if outcome == "not_found":
        return not_found
    if outcome == "error":
        return ERROR
    if outcome == "handoff" and verdict not in REACTIONS:
        return HANDOFF
    hedged = label["stance"] == "hedged"
    if verdict in REACTIONS:
        if verdict == "partial" and verdict_coverage:
            c = coverage_fraction(verdict_coverage)
            return c * ANSWER["confirmed"][hedged] + (1 - c) * not_found
        base = ANSWER[verdict][hedged]
    else:
        base = GROUNDING.get(grounding, GROUNDING["partly_supported"])[hedged]
    if outcome == "partial_answer":
        c = coverage_fraction(label["coverage"])
        return c * base + (1 - c) * not_found
    return base


def expected(dist: dict[str, float], points) -> float:
    return sum(p * points(value) for value, p in dist.items())


def score_step(step: dict, lookups: int) -> dict:
    """One agent step's cost, outcome and line items. `step` carries its label,
    its reaction (the user's label whose verdict is about it, or None) and
    Jev's answers keyed by rubric. `lookups` is the number of read-only tool calls before it in its
    task, which sets the task's "not found" points."""
    label, checks = step["label"], step.get("checks") or {}
    parts: list[dict] = []
    cost, plain_cost = 0.0, 0.0
    mismatch = unapproved = 0.0
    if label["type"] == "tool_call":
        side_effect = label["effect"] == "side_effect"
        cost = COST_TOOL_SIDE_EFFECT if side_effect else COST_TOOL_READ
        parts.append(
            {"text": "Standard cost of an action that changes or records something", "value": cost}
            if side_effect
            else {"text": "Standard cost of a lookup", "value": cost}
        )
        if label["result"] == "error":
            cost += COST_TOOL_ERROR_EXTRA
            parts.append(
                {"text": "Penalty because it returned an error", "value": COST_TOOL_ERROR_EXTRA}
            )
        if label.get("duplicate_of"):
            cost += COST_DUPLICATE_EXTRA
            parts.append(
                {
                    "text": "Penalty because it repeats an earlier call",
                    "value": COST_DUPLICATE_EXTRA,
                }
            )
        plain_cost = cost
        args = resolved("args_match", label.get("args_match") or "match", checks)
        mismatch = args.get("mismatch", 0.0)
        if mismatch:
            parts.append(
                {
                    "text": "Penalty because its arguments don't match what the user asked",
                    "value": round(mismatch * COST_ARGS_MISMATCH_EXTRA, 4),
                }
            )
        if label.get("args_match") != "unclear":
            plain_cost += mismatch * COST_ARGS_MISMATCH_EXTRA
        if side_effect:
            approval = resolved("approved", label.get("approved") or "yes", checks)
            unapproved = approval.get("no", 0.0)
            if unapproved:
                parts.append(
                    {
                        "text": "Penalty because the user hadn't approved the change",
                        "value": round(unapproved * COST_UNAPPROVED_EXTRA, 4),
                    }
                )
            if label.get("approved") != "unclear":
                plain_cost += unapproved * COST_UNAPPROVED_EXTRA
        cost += mismatch * COST_ARGS_MISMATCH_EXTRA + unapproved * COST_UNAPPROVED_EXTRA
    elif label["type"] == "clarifying_question":
        cost = plain_cost = COST_CLARIFYING
        parts.append({"text": "Standard cost of asking the user a question", "value": cost})
    elif label["type"] == "status_update":
        parts.append({"text": "Progress update (free)", "value": 0.0})

    base = cost
    outcome = plain_outcome = None
    verdict_dist: dict[str, float] = {}
    if label["is_output"]:
        reaction = step.get("reaction") or {}
        verdict_coverage = reaction.get("verdict_coverage")
        verdict_dist = resolved("verdict", reaction.get("verdict") or "none", checks)
        grounding_dist = resolved("grounding", label.get("grounding") or "partly_supported", checks)
        tier = not_found_tier(lookups, label.get("next_steps"))
        nf = NOT_FOUND[tier]

        def points(verdict: str) -> float:
            return expected(
                grounding_dist, lambda g: answer_points(label, verdict, g, nf, verdict_coverage)
            )

        outcome = expected(verdict_dist, points)
        plain_verdict = (
            {FALLBACK["verdict"]: 1.0} if reaction.get("verdict") == "unclear" else verdict_dist
        )
        plain_grounding = (
            {FALLBACK["grounding"]: 1.0} if label.get("grounding") == "unclear" else grounding_dist
        )
        plain_outcome = expected(
            plain_verdict,
            lambda v: expected(
                plain_grounding, lambda g: answer_points(label, v, g, nf, verdict_coverage)
            ),
        )
        parts.append(
            {
                "text": describe_output(label, verdict_dist, grounding_dist, tier),
                "value": round(outcome, 4),
            }
        )
        base += outcome

    graded, step_check = None, None
    for rubric in ("tool", "clarifying_question"):
        if rubric in checks:
            levels = CHECKS[rubric][1]
            probabilities = checks[rubric]["probabilities"]
            graded = sum(probabilities.get(i, 0.0) * v for i, (_, _, v) in enumerate(levels))
            step_check = rubric
            cost = min(0.0, cost + graded) if rubric == "tool" else cost - COST_CLARIFYING + graded
    return {
        "cost": cost,
        "plain_cost": plain_cost,
        "outcome": outcome,
        "plain_outcome": plain_outcome,
        "verdict": likeliest(verdict_dist) if verdict_dist else None,
        "fault": label["type"] == "tool_call"
        and (
            label["result"] == "error"
            or bool(label.get("duplicate_of"))
            or mismatch >= 0.5
            or unapproved >= 0.5
        ),
        "base": base,
        "parts": parts,
        "graded": graded,
        "check": step_check,
    }


def describe_output(
    label: dict, verdict: dict[str, float], grounding: dict[str, float], tier: str
) -> str:
    outcome = label["outcome"] or "answer"
    text = OUTCOME_WORDS.get(outcome, "Gave an answer")
    if outcome == "not_found":
        return f"{text} {NOT_FOUND_WORDS[tier]}"
    if outcome == "error":
        return text
    v = likeliest(verdict)
    if outcome in ("answer", "partial_answer") and label["stance"]:
        text += " with caveats" if label["stance"] == "hedged" else " without caveats"
    if outcome == "partial_answer" and label["coverage"] and "/" in label["coverage"]:
        done, asked = label["coverage"].split("/", 1)
        text += f" ({done} of {asked} items)"
    if v in REACTIONS or outcome == "handoff":
        return f"{text}, and {VERDICT_WORDS.get(v, v)}"
    return f"{text}; nobody reacted, and {GROUNDING_WORDS.get(likeliest(grounding), 'its grounding is unclear')}"


def checks_for(label: dict, reaction: dict | None) -> list[str]:
    """Which questions Jev is asked about a labeled agent step: one per tool
    call and clarifying question, and one per label marked "unclear". An
    answer the user reacted to is never judged; the reaction sets its points.
    `reaction` is the user's label whose verdict is about this step, if any."""
    asked = []
    if label["type"] == "tool_call":
        asked.append("tool")
        if label.get("args_match") == "unclear":
            asked.append("args_match")
        if label["effect"] == "side_effect" and label.get("approved") == "unclear":
            asked.append("approved")
    elif label["type"] == "clarifying_question":
        asked.append("clarifying_question")
    if label["is_output"] and label["outcome"] in ANSWER_OUTCOMES:
        reacted = (reaction or {}).get("verdict")
        if reacted == "unclear":
            asked.append("verdict")
        if label.get("grounding") == "unclear" and reacted not in REACTIONS:
            asked.append("grounding")
    return asked


def score_trace(agent_steps: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    """Credit assignment and task scores.

    agent_steps: agent chunks in order, each {chunk_id, task_id, label,
    reaction (the user's label reacting to it, or None), checks ({rubric:
    answer})}. Returns ({chunk_id: reward}, [task score]).

    An answer the user reacted to keeps 70% of its points and splits 30%
    equally: among the steps it used when confirmed or accepted, among the
    earlier faulty steps in its task when rejected or partly right. With no
    such steps it keeps everything. Sharing never changes a task's score.
    """
    rows = []
    lookups: dict[str, int] = {}
    for step in agent_steps:
        scored = score_step(step, lookups.get(step["task_id"], 0))
        if step["label"]["type"] == "tool_call" and step["label"]["effect"] != "side_effect":
            lookups[step["task_id"]] = lookups.get(step["task_id"], 0) + 1
        rows.append({**step, **scored, "shared": [], "kept": scored["outcome"]})

    tasks: dict[str, list[dict]] = {}
    for row in rows:
        tasks.setdefault(row["task_id"], []).append(row)
    episodes = []
    for task_id, task_rows in tasks.items():
        outputs = [i for i, r in enumerate(task_rows) if r["outcome"] is not None]
        penalty = plain_penalty = 0.0
        for n, i in enumerate(outputs):
            answer = task_rows[i]
            if (
                answer["verdict"] not in REACTIONS
                or answer["label"]["outcome"] not in ANSWER_OUTCOMES
            ):
                continue
            if n < len(outputs) - 1:
                penalty += EARLIER_PENALTY.get(answer["verdict"], 0.0)
                if (answer.get("reaction") or {}).get("verdict") != "unclear":
                    plain_penalty += EARLIER_PENALTY.get(answer["verdict"], 0.0)
            if answer["verdict"] in ("confirmed", "implicit_positive"):
                used = set(answer["label"].get("uses") or [])
                recipients = [
                    r
                    for r in task_rows[:i]
                    if r["chunk_id"] in used
                    and r["label"]["type"] in ("tool_call", "clarifying_question")
                ]
            else:
                recipients = [r for r in task_rows[:i] if r["fault"]]
            if not recipients:
                continue
            share = (1 - KEEP) * answer["outcome"] / len(recipients)
            answer["kept"] = KEEP * answer["outcome"]
            for r in recipients:
                r["shared"].append(
                    {
                        "from": answer["chunk_id"],
                        "verdict": answer["verdict"],
                        "value": round(share, 4),
                    }
                )
        costs = max(TASK_COST_CAP, sum(r["cost"] for r in task_rows))
        plain_costs = max(TASK_COST_CAP, sum(r["plain_cost"] for r in task_rows))
        final = task_rows[outputs[-1]] if outputs else None
        answer_score = final["outcome"] if final else 0.0
        plain_answer = final["plain_outcome"] if final else 0.0
        episodes.append(
            {
                "task": task_id,
                "score": round(clamp(answer_score + costs + penalty), 4),
                "rubric_b_only": round(clamp(plain_answer + plain_costs + plain_penalty), 4),
                "answer": round(answer_score, 4) if final else None,
                "costs": round(costs, 4),
                "earlier_answers": round(penalty, 4),
                "has_answer": final is not None,
            }
        )

    rewards = {}
    for row in rows:
        own = row["cost"] + (row["kept"] or 0.0)
        parts = list(row["parts"])
        if row["outcome"] is not None and row["kept"] != row["outcome"]:
            parts.append(
                {
                    "text": "Shared 30% with the steps that led to it",
                    "value": round(row["kept"] - row["outcome"], 4),
                }
            )
        shared_total = sum(s["value"] for s in row["shared"])
        check = None
        if row["check"] is not None:
            question, levels = CHECKS[row["check"]]
            probabilities = row["checks"][row["check"]]["probabilities"]
            level = max(range(len(levels)), key=lambda i: probabilities.get(i, 0.0))
            check = {
                "rubric": row["check"],
                "grader": row["checks"][row["check"]]["grader"],
                "question": question,
                "level": level,
                "text": levels[level][0],
                "short": levels[level][1],
                "value": round(row["graded"], 4),
                "probability": probabilities.get(level),
                "mode": "adjust" if row["check"] == "tool" else "replace",
            }
        rewards[row["chunk_id"]] = {
            "base": round(sum(p["value"] for p in parts), 4),
            "base_parts": parts,
            "jev": check,
            "labels_resolved": {
                field: row["checks"][field]["probabilities"]
                for field in LABEL_CHECKS
                if field in (row.get("checks") or {})
            },
            "score": round(clamp(own), 4),
            "shared": row["shared"],
            "shared_total": round(shared_total, 4),
            "total": round(clamp(own + shared_total), 4),
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
