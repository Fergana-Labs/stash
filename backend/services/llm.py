"""Direct Claude completions for non-agent, non-tool-use tasks.

Lives next to agent_runtime.py. Use this when you need a one-shot
synthesis from Claude with no MCP tools, no multi-turn loop, no SSE
streaming — e.g. generating UI copy, classifying a snippet, returning
structured JSON. The Agent SDK in agent_runtime.py is the wrong primitive
for those tasks.

Single source of truth for the Anthropic Python SDK across the backend.
"""

from __future__ import annotations

import enum
import json
import logging
import re

from anthropic import AsyncAnthropic

from ..config import settings

logger = logging.getLogger(__name__)


class ModelTier(enum.Enum):
    """Two-tier model selection for non-agent Claude calls.

    QUALITY = Sonnet (settings.ANTHROPIC_MODEL). Use for reasoning, the
    ask-the-workspace loop, anything user-facing where accuracy matters.

    FAST = Haiku (settings.ANTHROPIC_FAST_MODEL). Use for short
    classification / synthesis / structured-output tasks where speed
    and cost matter and Sonnet would be overkill."""

    QUALITY = "quality"
    FAST = "fast"


def _model_for(tier: ModelTier) -> str:
    if tier == ModelTier.QUALITY:
        return settings.ANTHROPIC_MODEL
    return settings.ANTHROPIC_FAST_MODEL


_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set on the backend")
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def complete_text(
    *,
    prompt: str,
    system: str | None = None,
    tier: ModelTier = ModelTier.FAST,
    max_tokens: int = 1024,
) -> str:
    """One-shot Claude completion. Returns concatenated assistant text."""
    client = _get_client()
    kwargs: dict = {
        "model": _model_for(tier),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    msg = await client.messages.create(**kwargs)
    return "".join(getattr(b, "text", "") for b in msg.content)


_JSON_FENCE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


async def complete_json(
    *,
    prompt: str,
    system: str | None = None,
    tier: ModelTier = ModelTier.FAST,
    max_tokens: int = 1024,
) -> dict:
    """One-shot Claude completion that returns parsed JSON.

    Strips markdown code fences if present, then json.loads. Raises
    json.JSONDecodeError if the response can't be parsed."""
    text = await complete_text(prompt=prompt, system=system, tier=tier, max_tokens=max_tokens)
    m = _JSON_FENCE.search(text)
    payload = (m.group(1) if m else text).strip()
    return json.loads(payload)
