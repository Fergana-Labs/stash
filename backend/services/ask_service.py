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
    prompt: str,
    user_id: UUID,
) -> AsyncIterator[str]:
    """Run the agent and yield SSE-encoded chunks.

    The ask endpoint is single-turn today: one user prompt in, one streamed
    response out. When multi-turn follow-ups land, do them through the SDK's
    native session resumption (`ClaudeAgentOptions(resume=session_id)`),
    not by stuffing prior turns into the prompt string."""
    system = prompts.render_ask_system(workspace_name)
    async for chunk in agent_runtime.stream_agent(
        system=system,
        prompt=prompt,
        workspace_id=workspace_id,
        user_id=user_id,
    ):
        yield chunk
