"""Pi agent stdin payload -> canonical HookEvent.

Pi uses executable hook files in ~/.pi/hooks/ — one file per event:
session_start, user_message, tool_use, assistant_message, session_end.
Each hook receives JSON on stdin with event-specific fields.

Common input fields (every event): session_id, cwd, hook_event_name.
Turn-scoped events add turn_id.

Per-event extras:
  session_start     {model, ...}
  user_message      {turn_id, prompt}
  tool_use          {turn_id, tool_name, tool_input, tool_use_id}
  assistant_message {turn_id, last_assistant_message}
  session_end       {}

Pi tool names are lowercase native names:
  bash, read, write, edit, grep, url_open, ask_followup, question,
  search, memory, think, execute_command, use_mcp_tool
"""

from __future__ import annotations

from stashai.plugin.event import HookEvent

_TOOL_MAP = {
    "bash": "bash",
    "read": "read",
    "write": "write",
    "edit": "edit",
    "grep": "grep",
    "url_open": "webfetch",
    "ask_followup": "ask",
    "question": "ask",
    "search": "ask",
    "memory": "think",
    "think": "think",
    "execute_command": "bash",
    "use_mcp_tool": "mcp",
}
_EXTRA_KEYS = ("model",)


def _normalize(name: str) -> str:
    return _TOOL_MAP.get(name.lower(), name.lower())


def _extras(data: dict) -> dict:
    return {key: data[key] for key in _EXTRA_KEYS if isinstance(data.get(key), str) and data[key]}


def adapt_session_start(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_start",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        extras=_extras(data),
    )


def adapt_prompt(data: dict) -> HookEvent:
    return HookEvent(
        kind="prompt",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        prompt_text=data.get("prompt", ""),
        extras=_extras(data),
    )


def adapt_tool_use(data: dict) -> HookEvent:
    tool_input = data.get("tool_input", {}) or {}
    if isinstance(tool_input, str):
        tool_input = {"raw": tool_input}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        tool_name=_normalize(data.get("tool_name", "")),
        tool_input=tool_input,
        tool_response=data.get("tool_response"),
        extras=_extras(data),
    )


def adapt_stop(data: dict) -> HookEvent:
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=data.get("last_assistant_message", ""),
        extras=_extras(data),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        extras=_extras(data),
    )
