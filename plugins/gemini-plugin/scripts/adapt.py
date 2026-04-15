"""Gemini CLI stdin payload -> canonical HookEvent.

Gemini hook payloads (per github.com/google-gemini/gemini-cli docs/hooks, 2026-04):
  SessionStart   {session_id, cwd}
  BeforeAgent    {session_id, prompt, cwd}
  AfterTool      {session_id, tool_name, tool_args, tool_result, cwd}
  AfterAgent     {session_id, last_message, cwd}
  SessionEnd     {session_id}

Gemini splits Claude's `PostToolUse` into `BeforeTool`/`AfterTool` — we only
listen on `AfterTool` since we want the result too.
"""

from __future__ import annotations

from event import HookEvent

_TOOL_MAP = {
    "read_file": "read",
    "write_file": "write",
    "edit_file": "edit",
    "replace": "edit",
    "shell": "bash",
    "run_shell_command": "bash",
    "glob": "glob",
    "grep": "grep",
    "web_fetch": "webfetch",
    "google_web_search": "websearch",
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
        prompt_text=data.get("prompt", data.get("user_message", "")),
    )


def adapt_tool_use(data: dict) -> HookEvent:
    args = data.get("tool_args", data.get("args", {}))
    if isinstance(args, str):
        args = {"raw": args}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        tool_name=_normalize(data.get("tool_name", "")),
        tool_input=args,
        tool_response=data.get("tool_result", data.get("result")),
    )


def adapt_stop(data: dict) -> HookEvent:
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=data.get("last_message", data.get("response", "")),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("session_id", ""),
    )
