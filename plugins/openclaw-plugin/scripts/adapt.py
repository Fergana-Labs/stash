"""Openclaw stdin payload -> canonical HookEvent.

Openclaw hook payloads (as documented at openclaw.dev/docs/hooks, 2026-04):
  session.start   {sessionId, workspaceUri}
  prompt.submit   {sessionId, message, workspaceUri}
  tool.after      {sessionId, tool, input, output, workspaceUri}
  turn.end        {sessionId, finalMessage, workspaceUri}
  session.end     {sessionId, workspaceUri}

Openclaw uses dotted tool names (e.g. `file.edit`); we flatten to Octopus's
canonical lowercase set.
"""

from __future__ import annotations

from event import HookEvent

_TOOL_MAP = {
    "file.edit": "edit",
    "file.write": "write",
    "file.read": "read",
    "shell.run": "bash",
    "shell.exec": "bash",
    "search.grep": "grep",
    "search.glob": "glob",
    "web.fetch": "websearch",
    "web.search": "websearch",
}


def _normalize(name: str) -> str:
    return _TOOL_MAP.get(name, name.lower())


def _cwd(data: dict) -> str:
    return data.get("cwd", data.get("workspaceUri", ""))


def adapt_session_start(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_start",
        session_id=data.get("sessionId", data.get("session_id", "")),
        cwd=_cwd(data),
    )


def adapt_prompt(data: dict) -> HookEvent:
    return HookEvent(
        kind="prompt",
        session_id=data.get("sessionId", data.get("session_id", "")),
        cwd=_cwd(data),
        prompt_text=data.get("message", data.get("prompt", "")),
    )


def adapt_tool_use(data: dict) -> HookEvent:
    args = data.get("input", data.get("args", {}))
    if isinstance(args, str):
        args = {"raw": args}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("sessionId", data.get("session_id", "")),
        cwd=_cwd(data),
        tool_name=_normalize(data.get("tool", data.get("tool_name", ""))),
        tool_input=args,
        tool_response=data.get("output", data.get("result")),
    )


def adapt_stop(data: dict) -> HookEvent:
    return HookEvent(
        kind="stop",
        session_id=data.get("sessionId", data.get("session_id", "")),
        cwd=_cwd(data),
        last_assistant_message=data.get("finalMessage", data.get("response", "")),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("sessionId", data.get("session_id", "")),
        cwd=_cwd(data),
    )
