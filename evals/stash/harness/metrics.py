"""
Parse a trial's transcript.jsonl into a metrics dict.

The transcript format is one JSON line per SDK message. Each line has a
`sdk_type` discriminator: "assistant", "user", "result", "system".

Metrics computed:
- total_input_tokens, total_output_tokens, cache_read, cache_create
- tool_calls: {tool_name: count}
- wall_clock_s: from first to last message timestamp
- stash_first: bool — did the agent call `stash history` before any Grep/Read/Glob?
- rediscovery_count: number of Grep/Read on session_a_touched_paths
- time_to_first_edit_s: seconds from first message to first Edit/Write
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

REDISCOVERY_TOOLS = {"Grep", "Read", "Glob"}
EDIT_TOOLS = {"Edit", "Write"}


def load_transcript(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def compute_metrics(transcript_path: Path, touched_paths: list[str]) -> dict[str, Any]:
    msgs = load_transcript(transcript_path)
    tool_calls: dict[str, int] = {}
    tool_call_sequence: list[tuple[str, dict]] = []
    first_ts: str | None = None
    last_ts: str | None = None
    first_edit_ts: str | None = None
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}
    result_row = None

    for m in msgs:
        ts = m.get("_recorded_at")
        if ts and first_ts is None:
            first_ts = ts
        if ts:
            last_ts = ts

        sdk_type = m.get("sdk_type")
        if sdk_type == "result":
            result_row = m
            usage = m.get("usage", {}) or {}
            tokens["input"] += usage.get("input_tokens", 0) or 0
            tokens["output"] += usage.get("output_tokens", 0) or 0
            tokens["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
            tokens["cache_create"] += usage.get("cache_creation_input_tokens", 0) or 0

        if sdk_type == "assistant":
            for block in m.get("content", []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                tool = block.get("name", "?")
                tool_calls[tool] = tool_calls.get(tool, 0) + 1
                tool_call_sequence.append((tool, block.get("input", {})))
                if tool in EDIT_TOOLS and first_edit_ts is None:
                    first_edit_ts = ts

    stash_first = _compute_stash_first(tool_call_sequence)

    rediscovery = _count_rediscovery(tool_call_sequence, touched_paths)

    wall = None
    if first_ts and last_ts:
        wall = (parse_ts(last_ts) - parse_ts(first_ts)).total_seconds()

    ttfe = None
    if first_ts and first_edit_ts:
        ttfe = (parse_ts(first_edit_ts) - parse_ts(first_ts)).total_seconds()

    return {
        "tokens": tokens,
        "tool_calls": tool_calls,
        "total_tool_calls": sum(tool_calls.values()),
        "wall_clock_s": wall,
        "time_to_first_edit_s": ttfe,
        "stash_first": stash_first,
        "rediscovery_count": rediscovery,
        "sdk_result": result_row,
    }


def _compute_stash_first(seq: list[tuple[str, dict]]) -> bool:
    """True if a `stash history` Bash call appeared before any Grep/Read/Glob."""
    for tool, inp in seq:
        if tool == "Bash":
            cmd = str(inp.get("command", ""))
            if "stash history" in cmd or "stash notebooks" in cmd or "stash workspaces" in cmd:
                return True
        if tool in REDISCOVERY_TOOLS:
            return False
    return False


def _count_rediscovery(seq: list[tuple[str, dict]], touched_paths: list[str]) -> int:
    """Count Grep/Read calls that target a file Session A already touched."""
    count = 0
    for tool, inp in seq:
        if tool not in REDISCOVERY_TOOLS:
            continue
        target = inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
        for p in touched_paths:
            if p in target:
                count += 1
                break
    return count


def run_checks(checks: list[dict], worktree: Path, patch_diff: str) -> list[dict]:
    """Execute task.yaml checks against the worktree. Return list of results."""
    out = []
    for chk in checks:
        kind = chk["kind"]
        if kind == "path_contains":
            path = worktree / chk["path"]
            pattern = chk["pattern"]
            ok = path.exists() and pattern in path.read_text()
            out.append({"kind": kind, "path": chk["path"], "pattern": pattern, "pass": ok})
        elif kind == "diff_contains":
            pattern = chk["pattern"]
            # Only match added lines — diff_contains means "agent added this".
            added = "\n".join(
                line for line in patch_diff.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            )
            out.append({"kind": kind, "pattern": pattern, "pass": pattern in added})
        elif kind == "login_command_not_argument":
            main_py = worktree / "cli" / "main.py"
            ok = False
            if main_py.exists():
                src = main_py.read_text()
                ok = "def login(" in src and "typer.Argument" not in _login_block(src)
            out.append({"kind": kind, "pass": ok})
        elif kind == "pytest":
            import subprocess

            r = subprocess.run(
                chk["cmd"].split(), capture_output=True, text=True, cwd=str(worktree)
            )
            out.append({"kind": kind, "cmd": chk["cmd"], "pass": r.returncode == 0,
                        "stdout_tail": r.stdout[-500:]})
        else:
            out.append({"kind": kind, "pass": False, "error": "unknown check kind"})
    return out


def _login_block(src: str) -> str:
    """Return the text of the `login` function definition, roughly."""
    idx = src.find("def login(")
    if idx == -1:
        return ""
    end = src.find("\ndef ", idx + 1)
    return src[idx : end if end != -1 else idx + 2000]
