"""Claude Code stdin payload -> canonical HookEvent.

Claude Code hook stdin shapes (as of 2026-04):
  SessionStart     {session_id, cwd}
  UserPromptSubmit {prompt | userPrompt, cwd, session_id}
  PostToolUse      {tool_name, tool_input, tool_response, cwd, session_id}
  Stop             {last_assistant_message, transcript_path, cwd, session_id}
  SessionEnd       {session_id}
"""

from __future__ import annotations

from stashai.plugin.event import HookEvent

# Claude PascalCase tool names -> canonical lowercase
_TOOL_MAP = {
    "Edit": "edit", "Write": "write", "Read": "read",
    "Bash": "bash", "Glob": "glob", "Grep": "grep",
    "Agent": "agent", "Task": "agent",
    "WebFetch": "webfetch", "WebSearch": "websearch",
    "NotebookEdit": "edit",
}


def _normalize_tool(name: str) -> str:
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
        prompt_text=data.get("prompt", data.get("userPrompt", "")),
    )


def adapt_tool_use(data: dict) -> HookEvent:
    raw_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    if isinstance(tool_input, str):
        tool_input = {"raw": tool_input}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        tool_name=_normalize_tool(raw_name),
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


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("session_id", ""),
    )
