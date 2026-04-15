"""Codex CLI stdin payload -> canonical HookEvent.

Verified against openai/codex (codex-rs/hooks/src/, April 2026).

The `codex_hooks` feature (Stage::UnderDevelopment) implements a
Claude-Code-style engine: hooks.json in ~/.codex/, PascalCase event names,
JSON payload on stdin.

Common input fields (every event): session_id, cwd, hook_event_name,
transcript_path, model, permission_mode. Turn-scoped events add turn_id.

Per-event extras:
  SessionStart      {source: "startup"|"resume"|"clear"}
  UserPromptSubmit  {turn_id, prompt}
  PreToolUse        {turn_id, tool_name, tool_input, tool_use_id}
  PostToolUse       {turn_id, tool_name, tool_input, tool_response, tool_use_id}
  Stop              {turn_id, stop_hook_active, last_assistant_message}

Codex today hardcodes tool_name="Bash" for shell calls; non-shell tools do
not trigger PreToolUse/PostToolUse.

`notify` fallback (separate top-level config.toml key) passes JSON as
argv[last] with stdin nulled. Only emits `agent-turn-complete`.
"""

from __future__ import annotations

from event import HookEvent

_TOOL_MAP = {
    "Bash": "bash",
}


def _normalize(name: str) -> str:
    return _TOOL_MAP.get(name, name.lower())


def adapt_session_start(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_start",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
    )


def adapt_prompt(data: dict) -> HookEvent:
    return HookEvent(
        kind="prompt",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        prompt_text=data.get("prompt", ""),
    )


def adapt_tool_use(data: dict) -> HookEvent:
    tool_input = data.get("tool_input", {}) or {}
    if isinstance(tool_input, str):
        tool_input = {"command": tool_input}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        tool_name=_normalize(data.get("tool_name", "")),
        tool_input=tool_input,
        tool_response=data.get("tool_response"),
    )


def adapt_stop(data: dict) -> HookEvent:
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=data.get("last_assistant_message", ""),
        transcript_path=data.get("transcript_path", ""),
    )


def adapt_notify(data: dict) -> HookEvent:
    """Codex `notify` payload: kebab-case keys, no session_id.

    Payload: {type: "agent-turn-complete", thread-id, turn-id, cwd, client,
    input-messages, last-assistant-message}.
    """
    return HookEvent(
        kind="stop",
        session_id=data.get("thread-id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=data.get("last-assistant-message", ""),
    )
