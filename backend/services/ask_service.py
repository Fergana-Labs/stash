"""Ask-the-workspace tool-use loop.

Streams text + tool-use events as SSE. Backed by tool_loop.py (direct
Anthropic API + native tool-use), not the Agent SDK — running the CLI
under the hood led to MCP serialization errors and hallucinated
"let me use the Bash/Monitor tool" fallbacks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from . import llm, prompts, tool_loop


async def stream_ask(
    workspace_id: UUID,
    workspace_name: str,
    prompt: str,
    user_id: UUID,
) -> AsyncIterator[str]:
    """Run the ask-the-workspace tool-use loop and yield SSE chunks.

    Single-turn today: one user prompt in, one streamed response out.
    When multi-turn follow-ups land, plumb history through here as
    additional turns on the messages list inside tool_loop."""
    system = prompts.render_ask_system(workspace_name)
    async for chunk in tool_loop.stream_tool_loop(
        tier=llm.ModelTier.QUALITY,
        system=system,
        prompt=prompt,
        workspace_id=workspace_id,
        user_id=user_id,
        tool_set=prompts.ASK_TOOL_SET,
    ):
        yield chunk
