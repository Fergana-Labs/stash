"""Map stash tool-loop events to the Vercel AI SDK data-stream protocol (v1).

`useChat()` consumes this drop-in (its default `streamProtocol: 'data'`): each
line is `<code>:<json>\n`. We translate our {text|tool|tool_result|end} events to
text parts (0:), tool calls (9:), tool results (a:), and a finish part (d:).
Responses must carry the `x-vercel-ai-data-stream: v1` header below.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

DATA_STREAM_HEADERS = {
    "x-vercel-ai-data-stream": "v1",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

_FINISH = {"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}}


def _line(code: str, value) -> str:
    return f"{code}:{json.dumps(value, separators=(',', ':'))}\n"


async def to_data_stream(events: AsyncIterator[dict]) -> AsyncIterator[str]:
    """Translate tool-loop event dicts into AI SDK data-stream lines."""
    saw_end = False
    async for event in events:
        kind = event.get("type")
        if kind == "text":
            yield _line("0", event.get("delta") or "")
        elif kind == "tool":
            yield _line(
                "9",
                {
                    "toolCallId": event.get("id"),
                    "toolName": event.get("name"),
                    "args": event.get("args") or {},
                },
            )
        elif kind == "tool_result":
            yield _line(
                "a", {"toolCallId": event.get("id"), "result": {"ok": event.get("ok", True)}}
            )
        elif kind == "end":
            saw_end = True
            yield _line("d", _FINISH)
    if not saw_end:
        yield _line("d", _FINISH)
