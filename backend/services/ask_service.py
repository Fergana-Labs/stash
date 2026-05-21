"""Ask-the-workspace tool-use loop.

Streams text + tool-use events as SSE. Backed by tool_loop.py (direct
Anthropic API + native tool-use), not the Agent SDK — running the CLI
under the hood led to MCP serialization errors and hallucinated
"let me use the Bash/Monitor tool" fallbacks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from . import agent_runtime, prompts, tool_loop


async def stream_ask(
    workspace_id: UUID,
    workspace_name: str,
    messages: list[dict],
    user_id: UUID,
    tool_set: tuple[str, ...] = prompts.STASH_TOOL_SET,
) -> AsyncIterator[str]:
    """Run the ask-the-workspace tool-use loop and yield SSE chunks."""
    prompt = _flatten_conversation(messages)
    system = prompts.render_ask_system(workspace_name)
    async for chunk in tool_loop.stream_tool_loop(
        tier=agent_runtime.ModelTier.QUALITY,
        system=system,
        prompt=prompt,
        workspace_id=workspace_id,
        user_id=user_id,
        tool_set=tool_set,
    ):
        yield chunk


def _flatten_conversation(messages: list[dict]) -> str:
    """Convert a [{role, content}] list to a single prompt string."""
    if not messages:
        return ""
    if len(messages) == 1 and messages[0].get("role") == "user":
        return messages[0].get("content", "")
    parts = []
    for m in messages:
        role = m.get("role") or "user"
        content = m.get("content") or ""
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)
