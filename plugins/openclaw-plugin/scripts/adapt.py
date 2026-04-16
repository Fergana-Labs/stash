"""Openclaw post-shim payload -> canonical HookEvent.

Openclaw's real hook event shape is an `InternalHookEvent` from
openclaw/openclaw src/hooks/internal-hook-types.ts:
  { type, action, sessionKey, context, timestamp, messages }

Our TS handler (handler.ts) branches on `type`+`action` and normalizes each
supported case to a flat JSON payload which it pipes into the matching Python
hook script. Event mapping:

  command:new                 -> on_session_start.py {session_id, cwd}
  message:received            -> on_prompt.py        {session_id, prompt, cwd, channel_id}
  message:sent (success=true) -> on_stop.py          {session_id, last_assistant_message, cwd, channel_id}
  command:reset/stop          -> on_session_end.py   {session_id}

Openclaw's gateway has no tool-call visibility (coding agents run out-of-proc
and have their own Stash plugins), so there is no tool_use adapter.
"""

from __future__ import annotations

from stashai.plugin.event import HookEvent


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
