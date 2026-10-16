"""Versioned, source-bound evidence packets, separate from labels and opinions.

History is read through the public-events adapter. Target feedback is supervision,
never an input feature; future messages and agent-judge verdicts are excluded.
Long traces have explicit selected-span coverage, not fictitious full coverage.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from .corpus import digest, public_events
from .gallery import read_jsonl

SCHEMA = "website-evidence-v1"
MAX_TRACE_CHARS = 12_000
MAX_STEP_CHARS = 2400
MAX_SOURCE_CHARS = 8000


def clean(text):
    text = re.sub(r"data:image/[^\s\"']+", "[image bytes stored separately]", str(text))
    text = re.sub(
        r"(?i)(bearer\s+|[\"']?[\w-]*(?:api[_-]?key|api[_-]?token|password|secret|access[_-]?token)[\w-]*[\"']?\s*[=:]\s*[\"']?)[^\s,;\"']+",
        r"\1[redacted]",
        text,
    )
    text = re.sub(
        r"\b(?:sk-ant-|sk-proj-|ghp_|github_pat_)[A-Za-z0-9_-]+", "[redacted credential]", text
    )
    return text


def step(event, *, target_quote=""):
    kind = event.get("kind")
    text = (
        event.get("text", "")
        if kind == "message"
        else event.get("arguments", "")
        if kind == "call"
        else event.get("output", "")
    )
    text = clean(text if isinstance(text, str) else json.dumps(text))
    if target_quote:
        text = text.replace(target_quote, "[target feedback excluded]")
    return {
        "id": f"line-{event['line']}",
        "kind": kind,
        "role": event.get("role"),
        "tool": event.get("name"),
        "call_id": event.get("call_id"),
        "text": text[:MAX_STEP_CHARS],
        "clipped": len(text) > MAX_STEP_CHARS,
    }


def history_trace(path, before_line, *, target_quote=""):
    first, tail, count = None, [], 0
    for event in public_events(path):
        if event["line"] >= before_line:
            break
        if event["kind"] not in ("message", "call", "result"):
            continue
        count += 1
        normalized = step(event, target_quote=target_quote)
        if first is None and event.get("role") == "user":
            first = normalized
        tail.append(normalized)
        tail = tail[-8:]
    selected = ([first] if first and all(s["id"] != first["id"] for s in tail) else []) + tail
    while sum(len(s["text"]) for s in selected) > MAX_TRACE_CHARS:
        selected.pop(1 if len(selected) > 2 else 0)
    return {
        "steps": selected,
        "coverage": {
            "public_steps_before_target": count,
            "selected_steps": len(selected),
            "target_feedback_excluded": True,
            "future_steps_excluded": True,
            "complete": len(selected) == count and not any(s["clipped"] for s in selected),
        },
    }


def packet(brief, trace, image: Path, *, source=""):
    pixels = image.read_bytes()
    if len(pixels) > 16_000_000:
        raise ValueError("Oversized screenshot")
    source = clean(source)
    data = {
        "schema": SCHEMA,
        "request": clean(brief),
        "trace": trace,
        "source": {
            "text": source[:MAX_SOURCE_CHARS],
            "available": bool(source),
            "complete": len(source) <= MAX_SOURCE_CHARS,
        },
        "render": {"sha256": digest(pixels), "available": True},
    }
    return {"id": digest(json.dumps(data, sort_keys=True)), "input": data, "image_file": str(image)}


def from_example(row, candidates):
    image = Path(row["file"])
    if digest(image.read_bytes()) != row["sha256"]:
        raise ValueError("Screenshot changed after labeling")
    candidate = candidates.get(row.get("session_id"))
    if candidate and row.get("line"):
        source_path = Path(candidate["path"])
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError("History source is unavailable")
        trace = history_trace(source_path, row["line"], target_quote=row.get("quote", ""))
    else:
        trace = {
            "steps": [],
            "coverage": {
                "complete": False,
                "reason": "No recorded agent trajectory is attached to this screenshot",
            },
        }
    # The generic request keeps task/style prompts and label notes out of features.
    value = packet("Assess this website or product interface's visual design.", trace, image)
    value["supervision"] = {
        k: row.get(k)
        for k in (
            "id",
            "label",
            "partition",
            "group",
            "quote",
            "scope",
            "label_source",
            "human_reviewed",
            "autolabel_receipt",
            "partial_history",
        )
    }
    value["supervision"]["provenance"] = {
        "session_id": row.get("session_id"),
        "line": row.get("line"),
        "image_index": row.get("image_index"),
        "reference_image": row.get("scope") == "reference",
    }
    return value


def from_trial(root, identity):
    from .trace_judge import load_packet

    trial, _ = load_packet(root, identity)
    # Candidate skill text is excluded from reward inputs. It is an intervention
    # being optimized, not authoritative evidence of what Henry likes.
    steps = [
        {
            "id": s["id"],
            "kind": "message",
            "role": s["role"],
            "text": clean(s["content"]),
            "clipped": False,
        }
        for s in trial["trace"]
        if s["role"] != "system"
    ]
    trace = {
        "steps": steps,
        "coverage": {
            "complete": True,
            "kind": "single-turn generation; no agent tool calls or corrections",
        },
    }
    return packet(
        trial["brief"], trace, root / "artifacts" / identity / "website.png", source=trial["source"]
    )


def model_payload(value):
    """The only packet sent for activations; no labels, quotes, paths or judge text."""
    data = value["input"]
    if value["id"] != digest(json.dumps(data, sort_keys=True)):
        raise ValueError("Evidence packet was modified")
    pixels = Path(value["image_file"]).read_bytes()
    if digest(pixels) != data["render"]["sha256"]:
        raise ValueError("Screenshot changed after evidence packet was frozen")
    return {"id": value["id"], "input": data, "image_base64": base64.b64encode(pixels).decode()}


def prepare(source, history, output, *, fresh_human_holdout=False):
    from .protocol import load

    frozen = load(source)
    candidates = {r["session_id"]: r for r in read_jsonl(history / "candidates.jsonl")}
    values = [from_example(row, candidates) for row in frozen["examples"]]
    if fresh_human_holdout:
        if frozen.get("label_policy", "human_reviewed") != "human_reviewed" or any(
            row.get("human_reviewed") is not True or row.get("needs_review") is not False
            for row in frozen["examples"]
        ):
            raise ValueError("Fresh human holdout requires explicitly reviewed labels")
        if any(
            (source / name).exists()
            for name in ("classifier.json", "classifier-training.json", "activation-probe.json")
        ):
            raise ValueError("This source holdout was already used; prepare fresh examples")
    # Freeze the evidence rows independently of the old reward model/receipts.
    dataset = {
        "schema": SCHEMA,
        "source_experiment": frozen["sha256"],
        "label_policy": frozen.get("label_policy"),
        "heldout_status": "untouched_human_test"
        if fresh_human_holdout
        else "Previously used automatic pilot data; not an untouched human test",
        "examples": values,
    }
    dataset["sha256"] = digest(json.dumps(dataset, sort_keys=True))
    path = output / "evidence.json"
    if path.exists() and json.loads(path.read_text()) != dataset:
        raise ValueError("Evidence changed; use a new probe experiment directory")
    output.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataset, indent=2))
    # A fresh generation experiment, with no old reward pin or invalidated ledger.
    for name in ("experiment.json", "SKILL.md"):
        dest = output / name
        if dest.exists() and dest.read_bytes() != (source / name).read_bytes():
            raise ValueError("Generation experiment changed")
        dest.write_bytes((source / name).read_bytes())
    return dataset
