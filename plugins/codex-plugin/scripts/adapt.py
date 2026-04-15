"""Codex CLI stdin payload -> canonical HookEvent.

Codex hook payloads (per developers.openai.com/codex/hooks, experimental 2026-04):
  SessionStart     {session_id, cwd}
  UserPromptSubmit {session_id, prompt, cwd}
  PostToolUse      {session_id, tool_name, tool_input, tool_output, cwd}
                    (Bash-only today)
  Stop             {session_id, last_message, cwd}

notify stdin (stable fallback, set via config.toml):
  {type: "agent-turn-complete" | "agent-message", last-assistant-message, ...}
"""

from __future__ import annotations

from event import HookEvent

_TOOL_MAP = {
    "Bash": "bash",
    "shell": "bash",
    "apply_patch": "edit",
    "read_file": "read",
    "write_file": "write",
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
    tool_input = data.get("tool_input", {})
    if isinstance(tool_input, str):
        tool_input = {"command": tool_input}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        tool_name=_normalize(data.get("tool_name", "")),
        tool_input=tool_input,
        tool_response=data.get("tool_output", data.get("tool_response")),
    )


def adapt_stop(data: dict) -> HookEvent:
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=data.get("last_message", data.get("last_assistant_message", "")),
    )


def adapt_notify(data: dict) -> HookEvent:
    """Codex's `notify` fallback — fires at turn end regardless of hook flag."""
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=data.get("last-assistant-message", ""),
    )
