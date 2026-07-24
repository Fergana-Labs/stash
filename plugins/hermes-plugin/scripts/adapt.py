"""Hermes Agent shell-hook stdin payload -> canonical HookEvent.

Verified against hermes-agent.nousresearch.com/docs/user-guide/features/hooks
(Shell Hooks, July 2026).

Every event's stdin JSON has the same envelope:

  {hook_event_name, tool_name, tool_input, session_id, cwd, extra}

`tool_name`/`tool_input` are null for non-tool events. `extra` carries the
event-specific kwargs:

  on_session_start  {model, platform}
  pre_llm_call      {user_message, conversation_history, is_first_turn, model, platform}
  post_tool_call    {result, duration_ms, tool_call_id, ...}
  post_llm_call     {user_message, assistant_response, conversation_history, model, platform}
  on_session_end    {completed, interrupted, model, platform}

pre_llm_call / post_llm_call fire once per user turn (not once per API call
inside the tool loop), so they map cleanly to prompt / stop. Hermes exposes
no transcript path.
"""

from __future__ import annotations

from stashai.plugin.event import HookEvent

_TOOL_MAP = {
    "terminal": "bash",
    "process": "bash",
    "read_file": "read",
    "patch": "edit",
    "web_search": "websearch",
    "web_extract": "webfetch",
    "delegate_task": "agent",
}


def _normalize(name: str) -> str:
    return _TOOL_MAP.get(name, name.lower())


def _extra(data: dict) -> dict:
    extra = data.get("extra")
    return extra if isinstance(extra, dict) else {}


def _extras(data: dict) -> dict:
    extra = _extra(data)
    return {
        k: extra[k] for k in ("model", "platform") if isinstance(extra.get(k), str) and extra[k]
    }


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
        prompt_text=_extra(data).get("user_message", ""),
        extras=_extras(data),
    )


def adapt_tool_use(data: dict) -> HookEvent:
    tool_input = data.get("tool_input") or {}
    if isinstance(tool_input, str):
        tool_input = {"raw": tool_input}
    result = _extra(data).get("result")
    if result is not None and not isinstance(result, dict):
        result = {"raw": result}
    return HookEvent(
        kind="tool_use",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        tool_name=_normalize(data.get("tool_name") or ""),
        tool_input=tool_input,
        tool_response=result,
        extras=_extras(data),
    )


def adapt_stop(data: dict) -> HookEvent:
    return HookEvent(
        kind="stop",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        last_assistant_message=_extra(data).get("assistant_response", ""),
        extras=_extras(data),
    )


def adapt_session_end(data: dict) -> HookEvent:
    return HookEvent(
        kind="session_end",
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        extras=_extras(data),
    )
