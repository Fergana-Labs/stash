"""Shared Anthropic client + tier-aware model selection.

Three call sites depend on this:
- ask_service.stream_ask           → QUALITY (Sonnet) + tools
- handoff_curator.regenerate       → QUALITY (Sonnet) + tools
- session_summarizer.summarize_one → FAST (Haiku), one-shot, no tools

Centralising here keeps prompts, model names, and SDK construction in one
place. Provider-neutral wrappers would be premature — Anthropic is the
only LLM provider for these features.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from anthropic import AsyncAnthropic

from ..config import settings

logger = logging.getLogger(__name__)


class ModelTier(StrEnum):
    QUALITY = "quality"
    FAST = "fast"


class LLMNotConfiguredError(RuntimeError):
    """Raised when an LLM call is attempted with ANTHROPIC_API_KEY unset.

    Callers that want graceful degradation should catch this; callers that
    expect the key to be set (workers) let it propagate so the failure is
    visible in logs + retry counters.
    """


_client: AsyncAnthropic | None = None


def get_async_client() -> AsyncAnthropic:
    global _client
    if _client is not None:
        return _client
    if not settings.ANTHROPIC_API_KEY:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY is not set")
    _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def model_for(tier: ModelTier) -> str:
    if tier is ModelTier.QUALITY:
        return settings.ANTHROPIC_MODEL
    return settings.ANTHROPIC_FAST_MODEL


@dataclass(slots=True)
class OneShotResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


async def one_shot(
    tier: ModelTier,
    system: str,
    user: str,
    *,
    max_tokens: int = 2048,
) -> OneShotResult:
    """Non-streaming, no-tools generation. Used by the session summarizer."""
    client = get_async_client()
    model = model_for(tier)
    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return OneShotResult(
        text="".join(text_parts),
        input_tokens=int(resp.usage.input_tokens or 0),
        output_tokens=int(resp.usage.output_tokens or 0),
        model=model,
    )


@dataclass(slots=True)
class AgentLoopResult:
    text: str               # final assistant text (last turn)
    input_tokens: int       # cumulative across turns
    output_tokens: int      # cumulative across turns
    turns_used: int
    tool_calls_used: int
    model: str
    terminated_by: str      # 'end_turn' | 'max_turns' | 'max_tool_calls' | 'max_input_tokens'


@dataclass(slots=True)
class AgentLoopCaps:
    max_turns: int = 8
    max_tool_calls: int = 30
    max_input_tokens: int = 80_000
    max_output_tokens_per_turn: int = 4096


async def agent_loop(
    tier: ModelTier,
    *,
    system: str,
    messages: list[dict],
    tools: list[dict],
    execute_tool,  # async (name: str, args: dict) -> tuple[str, str]  (payload_json, short_summary)
    caps: AgentLoopCaps | None = None,
    on_tool_call=None,  # optional (name, args, summary) -> None for observability
) -> AgentLoopResult:
    """Multi-turn tool-calling loop with hard budget caps.

    Used by the handoff curator. ``execute_tool`` is dependency-injected so
    the curator can reuse the ask service's tool executors without circular
    imports.
    """
    caps = caps or AgentLoopCaps()
    client = get_async_client()
    model = model_for(tier)
    convo: list[dict] = list(messages)
    cumulative_input = 0
    cumulative_output = 0
    tool_calls = 0
    final_text = ""
    turn = -1
    terminated_by = "max_turns"

    for turn in range(caps.max_turns):
        resp = await client.messages.create(
            model=model,
            max_tokens=caps.max_output_tokens_per_turn,
            system=system,
            tools=tools,
            messages=convo,
        )
        cumulative_input += int(resp.usage.input_tokens or 0)
        cumulative_output += int(resp.usage.output_tokens or 0)

        assistant_blocks: list[dict[str, Any]] = []
        tool_uses = []
        turn_text_parts = []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                assistant_blocks.append({"type": "text", "text": block.text})
                turn_text_parts.append(block.text)
            elif btype == "tool_use":
                assistant_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
                tool_uses.append(block)
        convo.append({"role": "assistant", "content": assistant_blocks})
        if turn_text_parts:
            final_text = "".join(turn_text_parts)

        if resp.stop_reason != "tool_use" or not tool_uses:
            terminated_by = "end_turn"
            break

        if cumulative_input > caps.max_input_tokens:
            terminated_by = "max_input_tokens"
            break

        tool_results = []
        for tu in tool_uses:
            if tool_calls >= caps.max_tool_calls:
                terminated_by = "max_tool_calls"
                break
            try:
                payload, summary = await execute_tool(tu.name, dict(tu.input))
            except Exception as exc:
                payload, summary = (f'{{"error": "{exc}"}}', "error")
            tool_calls += 1
            if on_tool_call is not None:
                try:
                    on_tool_call(tu.name, dict(tu.input), summary)
                except Exception:
                    pass
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": payload}
            )
        if terminated_by == "max_tool_calls":
            break

        convo.append({"role": "user", "content": tool_results})

    return AgentLoopResult(
        text=final_text,
        input_tokens=cumulative_input,
        output_tokens=cumulative_output,
        turns_used=turn + 1,
        tool_calls_used=tool_calls,
        model=model,
        terminated_by=terminated_by,
    )
