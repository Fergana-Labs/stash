"""Ask-the-stash agent loop.

Streams text + tool-use events as Server-Sent Events. The agent runtime
(`agent_runtime`) handles model + tool plumbing via the Claude Agent SDK;
this module just renders the system prompt and forwards the SSE stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from . import agent_runtime, prompts


async def stream_ask(
    stash_id: UUID,
    stash_name: str,
    messages: list[dict],
    tool_set: tuple[str, ...] = prompts.STASH_TOOL_SET,
) -> AsyncIterator[str]:
    """Run the agent and yield SSE-encoded chunks.

    The SDK takes a single prompt string; we flatten the chat history into
    one user turn (consistent with how the previous hand-rolled loop seeded
    `messages`)."""
    prompt = _flatten_conversation(messages)
    system = prompts.render_ask_system(stash_name)
    async for chunk in agent_runtime.stream_agent(
        tier=agent_runtime.ModelTier.QUALITY,
        system=system,
        prompt=prompt,
        stash_id=stash_id,
        tool_set=tool_set,
    ):
        yield chunk


def _flatten_conversation(messages: list[dict]) -> str:
    """Convert a [{role, content}] list to a single prompt. The SDK's
    `query()` takes one user turn; multi-turn replay happens by tagging
    each turn with its role inline."""
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
