"""Ask-the-stash tool-use loop (onboarding's one-shot demo).

Streams text + tool-use events as SSE. Backed by tool_loop.py (direct
Anthropic API + native tool-use) with the read-only ASK_TOOL_SET.

Multi-turn chat and Slack run on the cloud agent instead — see
sprite_agent_service.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from . import llm, prompts, source_service, tool_loop


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_ask(
    owner_user_id: UUID,
    owner_name: str,
    prompt: str,
    user_id: UUID,
) -> AsyncIterator[str]:
    """Single-turn ask: one user prompt in, one streamed response out."""
    sources = await source_service.list_sources(owner_user_id, user_id)
    system = prompts.render_ask_system(owner_name, sources)
    async for event in tool_loop.stream_tool_loop(
        tier=llm.ModelTier.QUALITY,
        system=system,
        prompt=prompt,
        owner_user_id=owner_user_id,
        user_id=user_id,
        tool_set=prompts.ASK_TOOL_SET,
    ):
        yield _sse(event)
