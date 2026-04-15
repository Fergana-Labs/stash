"""Cursor stdin payload -> canonical HookEvent.

Cursor hook payloads (as documented at cursor.com/docs/agent/hooks, 2026-04):
  sessionStart         {session_id, cwd, workspace_path}
  beforeSubmitPrompt   {session_id, prompt, cwd}
  postToolUse          {session_id, tool_name, args, result, cwd}
  stop                 {session_id, last_assistant_message, cwd}
  sessionEnd           {session_id, cwd}
"""

from __future__ import annotations

from event import HookEvent

_TOOL_MAP = {
    "edit_file": "edit",
    "write_file": "write",
    "read_file": "read",
    "terminal": "bash",
    "run_terminal_cmd": "bash",
    "codebase_search": "grep",
    "grep_search": "grep",
    "file_search": "glob",
    "web_search": "websearch",
}


def _normalize(name: str) -> str:
    return _TOOL_MAP.get(name, name.lower())


def adapt_session_start(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_start",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", data.get("workspace_path", "")),
    )


def adapt_prompt(data: dict) -> HookEvent:
    return HookEvent(
        kind="prompt",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        prompt_text=data.get("prompt", data.get("user_message", "")),
    )


def adapt_tool_use(data: dict) -> HookEvent:
    args = data.get("args", data.get("tool_input", {}))
    if isinstance(args, str):
        args = {"raw": args}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        tool_name=_normalize(data.get("tool_name", "")),
        tool_input=args,
        tool_response=data.get("result", data.get("tool_response")),
    )


def adapt_stop(data: dict) -> HookEvent:
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=data.get("last_assistant_message", data.get("response", "")),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
    )
