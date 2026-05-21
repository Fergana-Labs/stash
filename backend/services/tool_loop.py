"""Direct Anthropic tool-use loop — no Agent SDK / Claude Code subprocess.

The Agent SDK in agent_runtime.py launches the `claude` CLI as a child
process and proxies our Python tools across an MCP boundary. That works
but: (a) MCP serialization is brittle, (b) Claude Code's built-in tools
leak in unless explicitly disabled, (c) the model knows it's the CLI and
hallucinates fallbacks like "let me use the Bash tool" or
"use the Monitor tool to run the stash CLI directly."

We're on the backend — direct DB access, direct embeddings, direct
everything. We don't need a CLI in the loop. This module runs the same
tools via Anthropic's native tool-use API: model returns tool_use blocks
→ we execute Python functions in-process → send tool_result back → loop
until end_turn.

Yields SSE-encoded events with the same wire format as the legacy
stream_agent so the frontend doesn't change: text deltas + tool calls
+ end marker.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from anthropic import AsyncAnthropic

from ..config import settings
from .agent_runtime import (
    ModelTier,
    _TOOLS_BY_NAME,
    _model_for,
    _user_ctx,
    _workspace_ctx,
)

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _anthropic_tools(tool_names: tuple[str, ...]) -> list[dict]:
    """Anthropic native tool-use shape, derived from the SDK tool objects."""
    out = []
    for name in tool_names:
        t = _TOOLS_BY_NAME[name]
        out.append(
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
        )
    return out


def _tool_text(handler_result: dict) -> str:
    """SdkMcpTool handlers return {'content': [{'type':'text','text': str}]}.
    Anthropic tool_result accepts a string — extract it."""
    blocks = handler_result.get("content") or []
    parts = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(str(b.get("text") or ""))
    return "\n".join(parts) if parts else ""


async def stream_tool_loop(
    *,
    tier: ModelTier,
    system: str,
    prompt: str,
    workspace_id: UUID,
    user_id: UUID | None = None,
    tool_set: tuple[str, ...],
    max_turns: int = 8,
) -> AsyncIterator[str]:
    """Run an Anthropic tool-use loop and yield SSE chunks."""
    if not settings.ANTHROPIC_API_KEY:
        yield _sse(
            {
                "type": "text",
                "delta": (
                    "Ask-the-workspace needs ANTHROPIC_API_KEY set on the backend. "
                    "Drop a key into backend/.env and restart."
                ),
            }
        )
        yield _sse({"type": "end"})
        return

    client = _get_client()
    model = _model_for(tier)
    tools = _anthropic_tools(tool_set)
    messages: list[dict] = [{"role": "user", "content": prompt}]

    workspace_token = _workspace_ctx.set(workspace_id)
    user_token = _user_ctx.set(user_id)
    try:
        for _ in range(max_turns):
            assistant_blocks: list[dict] = []
            tool_uses: list[dict] = []

            async with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
            ) as stream:
                async for event in stream:
                    etype = getattr(event, "type", None)
                    if etype == "content_block_start":
                        block = getattr(event, "content_block", None)
                        if block is not None and block.type == "tool_use":
                            # Surface the tool call to the UI immediately so
                            # the citations strip can start populating.
                            yield _sse(
                                {
                                    "type": "tool",
                                    "name": block.name,
                                    "args": {},
                                }
                            )
                    elif etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is not None and getattr(delta, "type", "") == "text_delta":
                            yield _sse({"type": "text", "delta": delta.text})

                final = await stream.get_final_message()

            # Capture the assistant's full message for the next loop iter,
            # and gather any tool_use blocks we need to execute.
            for block in final.content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif btype == "tool_use":
                    assistant_blocks.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
                    tool_uses.append(
                        {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input or {},
                        }
                    )

            messages.append({"role": "assistant", "content": assistant_blocks})

            if final.stop_reason != "tool_use" or not tool_uses:
                # end_turn, max_tokens, stop_sequence — we're done.
                break

            # Execute each tool, build tool_result blocks for the next turn.
            tool_results: list[dict] = []
            for use in tool_uses:
                executor = _TOOLS_BY_NAME.get(use["name"])
                if executor is None:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": use["id"],
                            "content": json.dumps({"error": f"unknown tool: {use['name']}"}),
                            "is_error": True,
                        }
                    )
                    continue
                try:
                    raw = await executor.handler(use["input"])
                    text = _tool_text(raw)
                except Exception as e:
                    logger.exception("tool %s failed", use["name"])
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": use["id"],
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True,
                        }
                    )
                    continue
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": use["id"],
                        "content": text or "(empty)",
                    }
                )

            messages.append({"role": "user", "content": tool_results})
    finally:
        _user_ctx.reset(user_token)
        _workspace_ctx.reset(workspace_token)

    yield _sse({"type": "end"})
