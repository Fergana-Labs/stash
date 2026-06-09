"""Ask-the-workspace tool-use loop.

Streams text + tool-use events as SSE. Backed by tool_loop.py (direct
Anthropic API + native tool-use), not the Agent SDK — running the CLI
under the hood led to MCP serialization errors and hallucinated
"let me use the Bash/Monitor tool" fallbacks.

`stream_ask` is single-turn (onboarding's one-shot demo). `stream_chat` is the
multi-turn agent chat: it persists each turn as session history events (so a
chat is a stored Session) and replays the whole conversation to the model.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from . import llm, memory_service, prompts, source_service, tool_loop

# Agent name stamped on chat history events — shows up in Sessions "By agent".
AGENT_NAME = "Stash Agent"


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_ask(
    workspace_id: UUID,
    workspace_name: str,
    prompt: str,
    user_id: UUID,
) -> AsyncIterator[str]:
    """Single-turn ask: one user prompt in, one streamed response out."""
    sources = await source_service.list_sources(workspace_id, user_id)
    system = prompts.render_ask_system(workspace_name, sources)
    async for event in tool_loop.stream_tool_loop(
        tier=llm.ModelTier.QUALITY,
        system=system,
        prompt=prompt,
        workspace_id=workspace_id,
        user_id=user_id,
        tool_set=prompts.ASK_TOOL_SET,
    ):
        yield _sse(event)


async def _load_history(
    workspace_id: UUID, session_id: str, user_id: UUID, limit: int | None = None
) -> list[dict]:
    """Rebuild the [{role, content}] conversation from stored session events.

    `limit` caps the replay to the most recent N turns — for the Slack agent's
    single ever-growing per-user session, older context is recalled via the
    `search_history` tool rather than replayed verbatim."""
    events = await memory_service.read_session_events(workspace_id, session_id, user_id)
    history: list[dict] = []
    for e in events:
        content = (e.get("content") or "").strip()
        if not content:
            continue
        if e["event_type"] == "user_message":
            history.append({"role": "user", "content": content})
        elif e["event_type"] == "assistant_message":
            history.append({"role": "assistant", "content": content})
    if limit is not None:
        return history[-limit:]
    return history


async def stream_chat(
    workspace_id: UUID,
    workspace_name: str,
    user_id: UUID,
    session_id: str,
    message: str,
) -> AsyncIterator[str]:
    """Multi-turn agent chat over a stored session. Persists the user turn,
    replays the full conversation to the model, streams the reply, then persists
    the assistant turn. The leading `session` event tells the client which
    session this chat lives in (so it can reload it later)."""
    history = await _load_history(workspace_id, session_id, user_id)

    # Persist the user's turn first, so the conversation survives even if the
    # stream is interrupted before the model replies.
    await memory_service.push_event(
        workspace_id,
        AGENT_NAME,
        "user_message",
        message,
        user_id,
        session_id=session_id,
    )
    history.append({"role": "user", "content": message})

    yield _sse({"type": "session", "session_id": session_id})

    sources = await source_service.list_sources(workspace_id, user_id)
    system = prompts.render_ask_system(workspace_name, sources)

    answer: list[str] = []
    async for event in tool_loop.stream_tool_loop(
        tier=llm.ModelTier.QUALITY,
        system=system,
        history=history,
        workspace_id=workspace_id,
        user_id=user_id,
        tool_set=prompts.ASK_TOOL_SET,
    ):
        if event.get("type") == "text":
            answer.append(event.get("delta") or "")
        yield _sse(event)

    final = "".join(answer).strip()
    if final:
        await memory_service.push_event(
            workspace_id,
            AGENT_NAME,
            "assistant_message",
            final,
            user_id,
            session_id=session_id,
        )


# --- BEGIN Slack agent (talk-to-Stash bot) — removable feature block ---
# How much of the per-user Slack session to replay each turn. The agent recalls
# older context via the search_history tool, so this bounds the live window.
SLACK_HISTORY_REPLAY_LIMIT = 30


async def run_chat(
    workspace_id: UUID,
    workspace_name: str,
    user_id: UUID,
    session_id: str,
    message: str,
) -> str:
    """Non-streaming multi-turn chat for non-SSE surfaces (the Slack agent).

    Same persistence + replay as `stream_chat`, but uses the artifact-creating
    `SLACK_TOOL_SET` and returns the final answer text instead of streaming
    (Slack wants one message). The agent core (tool_loop) is untouched."""
    history = await _load_history(
        workspace_id, session_id, user_id, limit=SLACK_HISTORY_REPLAY_LIMIT
    )
    await memory_service.push_event(
        workspace_id, AGENT_NAME, "user_message", message, user_id, session_id=session_id
    )
    history.append({"role": "user", "content": message})

    sources = await source_service.list_sources(workspace_id, user_id)
    system = prompts.render_ask_system(workspace_name, sources)

    answer: list[str] = []
    async for event in tool_loop.stream_tool_loop(
        tier=llm.ModelTier.QUALITY,
        system=system,
        history=history,
        workspace_id=workspace_id,
        user_id=user_id,
        tool_set=prompts.SLACK_TOOL_SET,
    ):
        if event.get("type") == "text":
            answer.append(event.get("delta") or "")

    final = "".join(answer).strip()
    if final:
        await memory_service.push_event(
            workspace_id, AGENT_NAME, "assistant_message", final, user_id, session_id=session_id
        )
    return final
# --- END Slack agent ---
