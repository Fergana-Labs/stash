"""Per-harness command building + transcript mapping for the cloud agent.

Each coding-agent CLI (Claude Code, Codex, opencode) runs headless on the
user's sprite and streams a JSON transcript. A Harness knows three things:
its argv for a turn, how to map its transcript lines to our event contract
({text, tool, tool_result} + result), and how it resumes a prior session.

Resume differs by harness:
  - Claude Code derives its CLI session id deterministically from ours, so no
    capture is needed — turn 1 passes --session-id, later turns --resume.
  - Codex and opencode mint a native id on turn 1 (thread_id / sessionID) that
    must be fed back later; we capture it from the transcript and store it
    (harness_sessions table).

The orchestration (locks, history, persistence, reseed) lives in
sprite_agent_service and is harness-agnostic; only this file is per-harness.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import deque
from dataclasses import dataclass

from ..database import get_pool
from . import model_provider

# Claude's complaint when --resume points at a transcript this box never had.
RESUME_MISSING_RE = re.compile(r"no conversation found", re.IGNORECASE)


async def get_native_id(session_id: str, harness_id: str) -> str | None:
    row = await get_pool().fetchrow(
        "SELECT native_id FROM harness_sessions WHERE session_id = $1 AND harness = $2",
        session_id,
        harness_id,
    )
    return row["native_id"] if row else None


async def set_native_id(session_id: str, harness_id: str, native_id: str) -> None:
    await get_pool().execute(
        "INSERT INTO harness_sessions (session_id, harness, native_id) VALUES ($1, $2, $3) "
        "ON CONFLICT (session_id, harness) DO UPDATE SET native_id = EXCLUDED.native_id",
        session_id,
        harness_id,
        native_id,
    )


class TurnState:
    """Per-turn bookkeeping while mapping a harness's transcript."""

    def __init__(self) -> None:
        self.tool_names: dict[str, str] = {}
        self.result_text: str | None = None
        self.error: str | None = None
        self.resume_missing = False
        self.native_id: str | None = None  # captured for resume (codex/opencode)
        # Last plain-text lines (CLI errors land here since Sprites merges
        # stderr into stdout) — surfaced when the CLI dies without a parsed
        # error, so "exited with code 1" carries the actual cause.
        self.unparsed: deque[str] = deque(maxlen=5)


@dataclass(frozen=True)
class Harness:
    id: str
    bin: str
    provider: model_provider.Provider
    # opencode addresses models as provider/model; the others don't need it.
    default_model: str | None = None


CLAUDE = Harness("claude-code", "claude", model_provider.ANTHROPIC)
CODEX = Harness("codex", "codex", model_provider.OPENAI)
# opencode drives OpenRouter's many models; GLM is the default hosted pick.
OPENCODE = Harness("opencode", "opencode", model_provider.OPENROUTER, default_model="z-ai/glm-5.2")

_BY_ID = {h.id: h for h in (CLAUDE, CODEX, OPENCODE)}


def get(harness_id: str) -> Harness:
    if harness_id not in _BY_ID:
        raise ValueError(f"unknown harness: {harness_id}")
    return _BY_ID[harness_id]


def session_key(harness: Harness, session_id: str, native_id: str | None) -> str | None:
    """The harness's id for this conversation.

    Claude's is a deterministic uuid derived from ours — the SAME id is used to
    create the session (turn 1, --session-id) and to resume it (later turns,
    --resume). Codex/opencode mint their own; we reuse the captured native id
    (None until turn 1 has run)."""
    if harness is CLAUDE:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"stash-agent:{session_id}"))
    return native_id


def build_argv(
    harness: Harness,
    prompt: str,
    *,
    session_key: str | None,
    resume: bool,
    system_prompt: str,
    disallowed_tools: list[str] | None = None,
) -> list[str]:
    """`session_key` is the id for this conversation (see session_key());
    `resume` says whether to continue an existing session vs create fresh."""
    if harness is CLAUDE:
        # Claude always carries its deterministic id: --session-id creates it on
        # turn 1, --resume continues that exact session on later turns.
        argv = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--resume" if resume else "--session-id",
            session_key,
            "--append-system-prompt",
            system_prompt,
            "--dangerously-skip-permissions",
        ]
        if disallowed_tools:
            argv += ["--disallowedTools", ",".join(disallowed_tools)]
        return argv

    if harness is CODEX:
        # Codex mints its own thread id and has no persistent system-prompt
        # flag; prepend the prompt and resume only with a captured id.
        full = f"{system_prompt}\n\n{prompt}"
        base = ["codex", "exec"]
        if resume and session_key:
            base += ["resume", session_key]
        return [
            *base,
            full,
            "--json",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        ]

    if harness is OPENCODE:
        full = f"{system_prompt}\n\n{prompt}"
        argv = [
            "opencode",
            "run",
            full,
            "-m",
            f"{harness.provider.id}/{harness.default_model}",
            "--format",
            "json",
            "--dangerously-skip-permissions",
        ]
        if resume and session_key:
            argv += ["-s", session_key]
        return argv

    raise ValueError(f"unhandled harness: {harness.id}")


def map_line(harness: Harness, line: str, state: TurnState) -> list[dict]:
    """One transcript stdout line → zero or more contract events."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        # Sprites merges stderr into stdout, so CLI warnings land here. Keep
        # them for exit-code diagnostics, and still catch the resume-missing
        # signal so we can reseed.
        state.unparsed.append(line.strip())
        if RESUME_MISSING_RE.search(line):
            state.resume_missing = True
        return []

    if harness is CLAUDE:
        return _map_claude(obj, state)
    if harness is CODEX:
        return _map_codex(obj, state)
    if harness is OPENCODE:
        return _map_opencode(obj, state)
    return []


# --- Claude Code (stream-json) ---------------------------------------------


def _map_claude(obj: dict, state: TurnState) -> list[dict]:
    kind = obj.get("type")
    if kind == "stream_event":
        event = obj.get("event") or {}
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                return [{"type": "text", "delta": delta["text"]}]
        return []
    if kind == "assistant":
        events = []
        for block in (obj.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use":
                state.tool_names[block["id"]] = block["name"]
                events.append(
                    {
                        "type": "tool",
                        "id": block["id"],
                        "name": block["name"],
                        "args": block.get("input") or {},
                    }
                )
        return events
    if kind == "user":
        events = []
        for block in (obj.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tool_id = block.get("tool_use_id") or ""
                events.append(
                    {
                        "type": "tool_result",
                        "id": tool_id,
                        "name": state.tool_names.get(tool_id, ""),
                        "ok": not block.get("is_error", False),
                    }
                )
        return events
    if kind == "result":
        # subtype "success" can still carry is_error (e.g. a rejected key).
        if obj.get("subtype") == "success" and not obj.get("is_error"):
            state.result_text = (obj.get("result") or "").strip()
        else:
            state.error = str(obj.get("result") or obj.get("subtype") or "unknown error")
        return []
    return []


# --- Codex (--json) --------------------------------------------------------


def _map_codex(obj: dict, state: TurnState) -> list[dict]:
    kind = obj.get("type")
    if kind == "thread.started":
        state.native_id = obj.get("thread_id")
        return []
    if kind == "item.completed":
        item = obj.get("item") or {}
        itype = item.get("type")
        if itype in ("assistant_message", "message") and item.get("text"):
            state.result_text = item["text"].strip()
            return [{"type": "text", "delta": item["text"]}]
        if itype == "command_execution" and item.get("command"):
            tool_id = item.get("id") or item["command"]
            return [
                {
                    "type": "tool",
                    "id": tool_id,
                    "name": "Bash",
                    "args": {"command": item["command"]},
                },
                {
                    "type": "tool_result",
                    "id": tool_id,
                    "name": "Bash",
                    "ok": item.get("exit_code", 0) == 0,
                },
            ]
        return []
    if kind == "error":
        state.error = str(obj.get("message") or f"codex error: {json.dumps(obj)[:400]}")
        return []
    return []


# --- opencode (--format json) ----------------------------------------------


def _map_opencode(obj: dict, state: TurnState) -> list[dict]:
    native = obj.get("sessionID") or (obj.get("part") or {}).get("sessionID")
    if native:
        state.native_id = native
    part = obj.get("part") or obj
    ptype = part.get("type")
    if ptype == "text" and part.get("text"):
        state.result_text = part["text"].strip()
        return [{"type": "text", "delta": part["text"]}]
    if ptype == "tool":
        st = part.get("state") or {}
        tool_id = part.get("id") or part.get("tool") or ""
        name = part.get("tool") or "tool"
        events = [{"type": "tool", "id": tool_id, "name": name, "args": st.get("input") or {}}]
        if st.get("status") in ("completed", "error"):
            events.append(
                {
                    "type": "tool_result",
                    "id": tool_id,
                    "name": name,
                    "ok": st.get("status") == "completed",
                }
            )
        return events
    if ptype == "error":
        # When the CLI omits `message`, the raw event is the only diagnostic —
        # dropping it once left four days of failures logged as the literal
        # string "opencode error".
        state.error = str(part.get("message") or f"opencode error: {json.dumps(obj)[:400]}")
        return []
    return []
