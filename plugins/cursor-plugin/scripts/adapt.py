"""Cursor stdin payload -> canonical HookEvent.

Verified against cursor.com/docs/hooks (April 2026).

Common fields (every event): conversation_id, generation_id, model,
hook_event_name, cursor_version, workspace_roots, user_email, transcript_path.

Per-event extras we care about:
  sessionStart         {session_id, is_background_agent, composer_mode}
  beforeSubmitPrompt   {prompt, attachments}
  postToolUse          {tool_name, tool_input, tool_output, tool_use_id, cwd, duration}
  afterAgentResponse   {text}
  stop                 {status, loop_count}
  sessionEnd           {session_id, reason, duration_ms, final_status}

Notes:
- `cwd` is only on tool events; fall back to workspace_roots[0].
- `beforeSubmitPrompt` does not carry a session_id; use conversation_id.
- `stop` has no final assistant text — use afterAgentResponse for that.
- Tool names are PascalCase: Shell, Read, Write, Grep, Delete, Task, MCP:<name>.
"""

from __future__ import annotations

from event import HookEvent

_TOOL_MAP = {
    "Shell": "bash",
    "Read": "read",
    "Write": "write",
    "Edit": "edit",
    "Grep": "grep",
    "Delete": "delete",
    "Task": "agent",
}


def _normalize(name: str) -> str:
    if name.startswith("MCP:"):
        return name
    return _TOOL_MAP.get(name, name.lower())


def _cwd(data: dict) -> str:
    if data.get("cwd"):
        return data["cwd"]
    roots = data.get("workspace_roots") or []
    if roots:
        return roots[0]
    return ""


def _sid(data: dict) -> str:
    return data.get("session_id") or data.get("conversation_id", "")


def adapt_session_start(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_start",
        session_id=_sid(data),
        cwd=_cwd(data),
    )


def adapt_prompt(data: dict) -> HookEvent:
    return HookEvent(
        kind="prompt",
        session_id=_sid(data),
        cwd=_cwd(data),
        prompt_text=data.get("prompt", ""),
    )


def adapt_tool_use(data: dict) -> HookEvent:
    tool_input = data.get("tool_input", {}) or {}
    if isinstance(tool_input, str):
        tool_input = {"raw": tool_input}
    # Cursor's tool_output is a JSON-stringified string.
    return HookEvent(
        kind="tool_use",
        session_id=_sid(data),
        cwd=_cwd(data),
        tool_name=_normalize(data.get("tool_name", "")),
        tool_input=tool_input,
        tool_response=data.get("tool_output"),
    )


def adapt_agent_response(data: dict) -> HookEvent:
    """afterAgentResponse: final assistant text for the turn."""
    return HookEvent(
        kind="stop",
        session_id=_sid(data),
        cwd=_cwd(data),
        last_assistant_message=data.get("text", ""),
    )


def adapt_stop(data: dict) -> HookEvent:
    # `stop` has no assistant text; we emit a stop without a message.
    return HookEvent(
        kind="stop",
        session_id=_sid(data),
        cwd=_cwd(data),
        transcript_path=data.get("transcript_path", ""),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=_sid(data),
        cwd=_cwd(data),
    )
