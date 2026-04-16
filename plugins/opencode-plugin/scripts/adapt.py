"""opencode stdin payload -> canonical HookEvent.

Note: our TS shim (plugin.ts) already normalizes opencode's native event shape
into the lowest-common-denominator JSON our Python side expects. This adapter
is therefore near-identical to the Claude adapter — it exists so that if
someone invokes these scripts directly (e.g. tests) the pattern stays uniform.

Payloads our TS shim emits:
  on_session_start.py  {session_id, cwd}
  on_prompt.py         {session_id, prompt, cwd}
  on_tool_use.py       {session_id, tool_name, tool_input, tool_response, cwd}
  on_stop.py           {session_id, last_assistant_message, cwd}
  on_session_end.py    {session_id}
"""

from __future__ import annotations

from stashai.plugin.event import HookEvent

_TOOL_MAP = {
    "edit": "edit",
    "write": "write",
    "read": "read",
    "bash": "bash",
    "glob": "glob",
    "grep": "grep",
    "task": "agent",
    "agent": "agent",
    "webfetch": "webfetch",
    "websearch": "websearch",
}


def _normalize(name: str) -> str:
    return _TOOL_MAP.get(name.lower(), name.lower())


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
    tin = data.get("tool_input", {})
    if isinstance(tin, str):
        tin = {"raw": tin}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        tool_name=_normalize(data.get("tool_name", "")),
        tool_input=tin,
        tool_response=data.get("tool_response"),
    )


def adapt_stop(data: dict) -> HookEvent:
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=data.get("last_assistant_message", ""),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("session_id", ""),
    )
