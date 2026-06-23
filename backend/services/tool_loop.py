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

Yields structured event dicts (the caller SSE-encodes them): `text` (assistant
text delta), `tool` (a tool call with its complete args, emitted once the input
JSON is fully accumulated), `tool_result` (that tool finished; `ok` says whether
it succeeded), and a final `end` marker.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from anthropic import AsyncAnthropic

from ..config import settings
from .agent_runtime import (
    _TOOLS_BY_NAME,
    _agent_name_ctx,
    _scope_ctx,
    _session_ctx,
    _user_ctx,
)
from .llm import ModelTier, _model_for

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


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
    prompt: str | None = None,
    history: list[dict] | None = None,
    owner_user_id: UUID,
    user_id: UUID | None = None,
    tool_set: tuple[str, ...],
    max_turns: int = 8,
    session_id: str | None = None,
    agent_name: str | None = None,
) -> AsyncIterator[dict]:
    """Run an Anthropic tool-use loop, yielding structured events (dicts):
    `text` / `tool` / `tool_result` / `end`. The caller is responsible for
    SSE-encoding. Pass `history` (a full [{role, content}] conversation) for a
    multi-turn chat, or `prompt` for a single user turn."""
    if not settings.ANTHROPIC_API_KEY:
        yield {
            "type": "text",
            "delta": (
                "Ask-the-stash needs ANTHROPIC_API_KEY set on the backend. "
                "Drop a key into backend/.env and restart."
            ),
        }
        yield {"type": "end"}
        return

    client = _get_client()
    model = _model_for(tier)
    tools = _anthropic_tools(tool_set)
    messages: list[dict] = (
        [dict(m) for m in history] if history else [{"role": "user", "content": prompt or ""}]
    )

    scope_token = _scope_ctx.set(owner_user_id)
    user_token = _user_ctx.set(user_id)
    session_token = _session_ctx.set(session_id)
    agent_name_token = _agent_name_ctx.set(agent_name)
    try:
        for turn_idx in range(max_turns):
            assistant_blocks: list[dict] = []
            tool_uses: list[dict] = []
            # The model's text after a tool call is a fresh thought, but its
            # deltas would otherwise jam straight onto the previous turn's text
            # ("…both topics!Both searches…"). Prepend one paragraph break before
            # the first text chunk of any continued turn — only when there is
            # follow-up text, so we never leave a trailing blank line.
            produced_text = False

            async with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
            ) as stream:
                # The SDK's stream yields typed helper events on top of the raw
                # API events. We use two:
                #   - "text": an assistant text delta (event.text), streamed live.
                #   - "content_block_stop": carries the *fully accumulated*
                #     content_block. For a tool_use block its `input` is the
                #     complete parsed object — the documented-safe point to read
                #     it. We deliberately ignore the raw `input_json_delta`
                #     events: streaming partial tool JSON to the UI is the jank
                #     we want to avoid. The tool surfaces once, with real args.
                async for event in stream:
                    etype = getattr(event, "type", None)
                    if etype == "text":
                        delta = event.text
                        if turn_idx > 0 and not produced_text:
                            delta = "\n\n" + delta
                        produced_text = True
                        yield {"type": "text", "delta": delta}
                    elif etype == "content_block_stop":
                        block = getattr(event, "content_block", None)
                        if block is not None and getattr(block, "type", None) == "tool_use":
                            yield {
                                "type": "tool",
                                "id": block.id,
                                "name": block.name,
                                "args": block.input or {},
                            }

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
            # Errors get a generic message in the wire payload and only
            # non-sensitive metadata in logs. Tool inputs can contain customer
            # queries, source handles, or transcript text.
            tool_results: list[dict] = []
            for use in tool_uses:
                executor = _TOOLS_BY_NAME.get(use["name"])
                ok = True
                if executor is None:
                    ok = False
                    logger.warning("agent requested unknown tool: %s", use["name"])
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": use["id"],
                            "content": "tool not available",
                            "is_error": True,
                        }
                    )
                else:
                    try:
                        raw = await executor.handler(use["input"])
                        text = _tool_text(raw)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": use["id"],
                                "content": text or "(empty)",
                            }
                        )
                    except Exception as exc:
                        ok = False
                        logger.error(
                            "tool %s failed exception_type=%s",
                            use["name"],
                            type(exc).__name__,
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": use["id"],
                                "content": "tool failed",
                                "is_error": True,
                            }
                        )
                # Tell the UI the tool finished. Tools execute after the model
                # stream closes, so without this the connection sits idle while
                # a slow tool (e.g. a lazy Drive/Notion fetch) runs — which reads
                # as a hang. The flag lets the UI drop a citation for a tool that
                # errored rather than claim it grounded the answer.
                yield {"type": "tool_result", "id": use["id"], "name": use["name"], "ok": ok}

            messages.append({"role": "user", "content": tool_results})
    finally:
        _agent_name_ctx.reset(agent_name_token)
        _session_ctx.reset(session_token)
        _user_ctx.reset(user_token)
        _scope_ctx.reset(scope_token)

    yield {"type": "end"}
