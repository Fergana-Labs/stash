"""Starter behaviors detected by rules over the step labels a trace already has.

The step labeler (rm/step_labeler.py) says what every step is: a user correction
or repeat, a tool call that came back empty or failed, an answer asserted
without caveats. Most behaviors teams first ask about are a pattern over those
labels, so they cost no model calls at all. Each rule returns windows
[start_idx, end_idx] with the evidence quotes that put them there.
"""

from __future__ import annotations

import re
from collections.abc import Callable

Window = dict  # {"start_idx", "end_idx", "confidence", "evidence": [{"idx", "quote"}], "note"}

QUOTE_CHARS = 200


def _quote(idx: int, text: str | None) -> dict:
    return {"idx": idx, "quote": (text or "")[:QUOTE_CHARS]}


def _window(start: int, end: int, evidence: list[dict], note: str = "") -> Window:
    return {
        "start_idx": start,
        "end_idx": end,
        "confidence": 1.0,
        "evidence": evidence,
        "note": note,
    }


def _ordered(labels: dict[str, dict]) -> list[tuple[int, dict]]:
    return sorted(((int(k), v) for k, v in labels.items()), key=lambda kv: kv[0])


def _user_where(field: str, value: str) -> Callable:
    def rule(labels: dict[str, dict], steps: list[dict]) -> list[Window]:
        return [
            _window(idx, idx, [_quote(idx, label.get("evidence"))])
            for idx, label in _ordered(labels)
            if label.get("actor") == "user" and label.get(field) == value
        ]

    return rule


def _tool_result(value: str) -> Callable:
    def rule(labels: dict[str, dict], steps: list[dict]) -> list[Window]:
        return [
            _window(idx, idx, [_quote(idx, label.get("evidence"))], label.get("tool") or "")
            for idx, label in _ordered(labels)
            if label.get("type") == "tool_call" and label.get("result") == value
        ]

    return rule


THROTTLED = re.compile(
    r"\b(429|rate[- ]?limit(ed)?|too many requests|timed? ?out|timeout|deadline exceeded)\b", re.I
)
HANDOFF = re.compile(
    r"\b((speak|talk) (to|with) (a )?(human|person|real person|manager|someone)|escalat\w*|agent please|representative)\b",
    re.I,
)


def throttled(labels: dict[str, dict], steps: list[dict]) -> list[Window]:
    out = []
    for step in steps:
        if step["role"] != "tool":
            continue
        match = THROTTLED.search(step.get("content") or "")
        if match:
            text = step["content"]
            start = max(0, match.start() - 60)
            out.append(
                _window(
                    step["idx"],
                    step["idx"],
                    [_quote(step["idx"], text[start : start + QUOTE_CHARS])],
                )
            )
    return out


def handoff_request(labels: dict[str, dict], steps: list[dict]) -> list[Window]:
    out = []
    for step in steps:
        if step["role"] != "user":
            continue
        match = HANDOFF.search(step.get("content") or "")
        if match:
            out.append(_window(step["idx"], step["idx"], [_quote(step["idx"], step["content"])]))
    return out


def premature_stop(labels: dict[str, dict], steps: list[dict]) -> list[Window]:
    """A lookup came back empty and the agent answered without trying anything else."""
    ordered = _ordered(labels)
    out = []
    for i, (idx, label) in enumerate(ordered):
        if not (label.get("type") == "tool_call" and label.get("result") == "empty"):
            continue
        for later_idx, later in ordered[i + 1 :]:
            if later.get("task_id") != label.get("task_id") or later.get("actor") == "user":
                break
            if later.get("is_output"):
                out.append(
                    _window(
                        idx,
                        later_idx,
                        [
                            _quote(idx, label.get("evidence")),
                            _quote(later_idx, later.get("evidence")),
                        ],
                        f"Stopped after an empty {label.get('tool') or 'tool'} result",
                    )
                )
                break
            if later.get("type") == "tool_call":
                break
    return out


def unsupported_claim(labels: dict[str, dict], steps: list[dict]) -> list[Window]:
    """An answer asserted without caveats in a task where no tool returned anything to back it."""
    ordered = _ordered(labels)
    out = []
    task_start: dict[str, int] = {}
    backed: set[str] = set()
    for idx, label in ordered:
        task = label.get("task_id") or ""
        task_start.setdefault(task, idx)
        if label.get("type") == "tool_call" and label.get("result") == "data":
            backed.add(task)
        if (
            label.get("is_output")
            and label.get("stance") == "asserted"
            and label.get("outcome") in ("answer", "partial_answer")
            and task not in backed
        ):
            out.append(
                _window(
                    task_start[task],
                    idx,
                    [_quote(idx, label.get("evidence"))],
                    "Asserted with no supporting tool result in this task",
                )
            )
    return out


def repeated_tool_call(labels: dict[str, dict], steps: list[dict]) -> list[Window]:
    """The same call again with nothing in between that could change its answer.

    Retrying after an error or a rate limit is recovery, and re-running a check
    after editing something is verification; neither is a wasted repeat."""
    ordered = _ordered(labels)
    by_chunk = {label.get("chunk_id"): (idx, label) for idx, label in ordered}
    out = []
    for idx, label in ordered:
        duplicate_of = label.get("duplicate_of") if label.get("type") == "tool_call" else None
        first = by_chunk.get(duplicate_of) if duplicate_of else None
        if first is None:
            continue
        first_idx, first_label = first
        if first_label.get("result") == "error":
            continue
        changed = any(
            first_idx < other_idx < idx and other.get("effect") == "side_effect"
            for other_idx, other in ordered
        )
        if changed:
            continue
        out.append(
            _window(
                first_idx,
                idx,
                [_quote(idx, label.get("evidence"))],
                f"Same call as step {first_idx + 1}",
            )
        )
    return out


# kind -> (rule, needs step labels)
RULES: dict[str, tuple[Callable, bool]] = {
    "repeat_request": (_user_where("intent", "repeat_request"), True),
    "user_correction": (_user_where("intent", "correction"), True),
    "user_frustration": (_user_where("sentiment", "negative"), True),
    "handoff_request": (handoff_request, False),
    "empty_tool_result": (_tool_result("empty"), True),
    "tool_error": (_tool_result("error"), True),
    "throttled": (throttled, False),
    "premature_stop": (premature_stop, True),
    "unsupported_claim": (unsupported_claim, True),
    "repeated_tool_call": (repeated_tool_call, True),
}

STARTERS = [
    {"slug": "repeat-request", "name": "Repeats the request", "actor": "user", "kind": "repeat_request",
     "definition": "The user asks for the same thing again after getting an answer: the answer missed."},
    {"slug": "user-correction", "name": "Corrects the agent", "actor": "user", "kind": "user_correction",
     "definition": "The user says or implies the agent was wrong and redirects it."},
    {"slug": "user-frustration", "name": "User frustration", "actor": "user", "kind": "user_frustration",
     "definition": "A user message with negative sentiment."},
    {"slug": "handoff-request", "name": "Asks for a human", "actor": "user", "kind": "handoff_request",
     "definition": "The user asks to escalate or talk to a person."},
    {"slug": "premature-stop", "name": "Stops after an empty lookup", "actor": "agent", "kind": "premature_stop",
     "definition": "A tool returned nothing and the agent answered without trying another way.", "severity": "high"},
    {"slug": "unsupported-claim", "name": "Claims without evidence", "actor": "agent", "kind": "unsupported_claim",
     "definition": "The agent asserts an answer with no caveats although no tool in the task returned anything to back it.",
     "severity": "high"},
    {"slug": "repeated-tool-call", "name": "Repeats a tool call", "actor": "agent", "kind": "repeated_tool_call",
     "definition": "The agent makes the exact same tool call again."},
    {"slug": "empty-tool-result", "name": "Empty tool result", "actor": "environment", "kind": "empty_tool_result",
     "definition": "A tool ran and returned nothing useful: no rows, no matches."},
    {"slug": "tool-error", "name": "Tool error", "actor": "environment", "kind": "tool_error",
     "definition": "A tool call failed."},
    {"slug": "throttled", "name": "Timeout or rate limit", "actor": "environment", "kind": "throttled",
     "definition": "A tool result reports a timeout or a rate limit."},
]  # fmt: skip


def needs_labels(rule: dict) -> bool:
    return RULES[rule["kind"]][1]


def merge(windows: list[Window]) -> list[Window]:
    """Overlapping or touching windows of one behavior become one window."""
    out: list[Window] = []
    for w in sorted(windows, key=lambda w: (w["start_idx"], w["end_idx"])):
        if out and w["start_idx"] <= out[-1]["end_idx"] + 1:
            last = out[-1]
            last["end_idx"] = max(last["end_idx"], w["end_idx"])
            last["evidence"] = last["evidence"] + w["evidence"]
            last["confidence"] = max(last["confidence"], w["confidence"])
            last["note"] = last["note"] or w["note"]
        else:
            out.append({**w, "evidence": list(w["evidence"])})
    return out


def detect(rule: dict, labels: dict[str, dict], steps: list[dict]) -> list[Window]:
    fn, _ = RULES[rule["kind"]]
    return merge(fn(labels, steps))
