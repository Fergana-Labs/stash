"""Gemini CLI stdin payload -> canonical HookEvent.

Verified against github.com/google-gemini/gemini-cli
(packages/core/src/hooks/types.ts, April 2026).

Common fields (every event): session_id, transcript_path, cwd,
hook_event_name, timestamp.

Per-event extras:
  SessionStart   {source}
  BeforeAgent    {prompt}
  AfterTool      {tool_name, tool_input, tool_response, mcp_context?}
  AfterAgent     {prompt, prompt_response, stop_hook_active}
  SessionEnd     {reason}

Notes:
- `tool_response` is an object: {llmContent, returnDisplay, error?}.
- MCP tools are named `mcp_<server>_<tool>`.
"""

from __future__ import annotations

from event import HookEvent

_TOOL_MAP = {
    "read_file": "read",
    "write_file": "write",
    "replace": "edit",
    "run_shell_command": "bash",
    "glob": "glob",
    "grep": "grep",
    "web_fetch": "webfetch",
    "google_web_search": "websearch",
    "read_many_files": "read",
    "list_directory": "ls",
    "write_todos": "todo",
    "save_memory": "memory",
}


def _normalize(name: str) -> str:
    if name.startswith("mcp_"):
        return name
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
        tool_input = {"raw": tool_input}
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
        last_assistant_message=data.get("prompt_response", ""),
        transcript_path=data.get("transcript_path", ""),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
    )
