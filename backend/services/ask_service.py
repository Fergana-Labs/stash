"""Ask-the-workspace agent loop.

Streams text + tool-use events as Server-Sent Events. The agent runtime
(`agent_runtime`) handles model + tool plumbing via the Claude Agent SDK;
this module just renders the system prompt and forwards the SSE stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from . import agent_runtime, prompts


async def stream_ask(
    workspace_id: UUID,
    workspace_name: str,
    messages: list[dict],
    user_id: UUID,
) -> AsyncIterator[str]:
    """Run the agent and yield SSE-encoded chunks.

    The SDK takes a single prompt string; we flatten the chat history into
    one user turn (consistent with how the previous hand-rolled loop seeded
    `messages`)."""
    prompt = _flatten_conversation(messages)
    system = prompts.render_ask_system(workspace_name)
    async for chunk in agent_runtime.stream_agent(
        system=system,
        prompt=prompt,
        workspace_id=workspace_id,
        user_id=user_id,
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
