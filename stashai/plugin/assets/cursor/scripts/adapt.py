"""Cursor stdin payload -> canonical HookEvent.

Verified against cursor.com/docs/hooks (April 2026).

Common fields (every event): conversation_id, generation_id, model,
hook_event_name, cursor_version, workspace_roots, user_email, transcript_path.

Per-event extras we care about:
  sessionStart         {session_id, is_background_agent, composer_mode}
  beforeSubmitPrompt   {prompt, attachments}
  postToolUse          {tool_name, tool_input, tool_output, tool_use_id, cwd, duration}
  afterAgentResponse   {text}
  sessionEnd           {session_id, reason, duration_ms, final_status}

Notes:
- `cwd` is only on tool events; fall back to workspace_roots[0].
- session_id is read from the payload when present (sessionStart / sessionEnd).
  All downstream streaming uses state.session_id (saved at sessionStart), so
  events without session_id (beforeSubmitPrompt, postToolUse, afterAgentResponse)
  produce HookEvents with empty session_id — that's fine, the field is unused
  on those code paths.
- `tool_output` is a JSON-stringified string — parse before handing to summarize_tool_use.
- Tool names are PascalCase: Shell, Read, Write, Grep, Delete, Task, MCP:<name>.
"""

from __future__ import annotations

import json

from stashai.plugin.event import HookEvent

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


def adapt_session_start(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_start",
        session_id=data.get("session_id", ""),
        cwd=_cwd(data),
    )


def adapt_prompt(data: dict) -> HookEvent:
    return HookEvent(
        kind="prompt",
        session_id=data.get("session_id", ""),
        cwd=_cwd(data),
        prompt_text=data.get("prompt", ""),
    )


def _parse_tool_output(raw) -> dict | None:
    """Cursor's tool_output is a JSON-stringified string; summarize_tool_use
    expects a dict. Parse it; fall back to {"raw": ...} for non-JSON text."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return {"raw": raw}
        return parsed if isinstance(parsed, dict) else {"raw": raw}
    return {"raw": str(raw)}


def adapt_tool_use(data: dict) -> HookEvent:
    tool_input = data.get("tool_input", {}) or {}
    if isinstance(tool_input, str):
        tool_input = {"raw": tool_input}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=_cwd(data),
        tool_name=_normalize(data.get("tool_name", "")),
        tool_input=tool_input,
        tool_response=_parse_tool_output(data.get("tool_output")),
    )


def adapt_agent_response(data: dict) -> HookEvent:
    """afterAgentResponse: final assistant text for the turn."""
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=_cwd(data),
        last_assistant_message=data.get("text", ""),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("session_id", ""),
        cwd=_cwd(data),
    )
