"""The Stash agent, running as a coding-agent CLI on the user's cloud computer.

Replaces the in-process tool loop for web chat and Slack: each turn execs a
harness CLI (Claude Code by default; see harness.py) on the user's sprite and
maps its transcript onto the event contract ({text, tool, tool_result, end}
plus {status, error}) that the web ChatPanel and Slack already consume.

Conversation state:
  - history_events in Postgres is the source of truth (a chat is a Session).
  - The harness's on-box transcript enables resume between turns; if it's gone
    (recreated sprite, restored checkpoint), the turn reseeds a fresh session
    from stored history — the box is cattle, the DB is not.
"""

from __future__ import annotations

import asyncio
import codecs
import json
import logging
import re
import secrets
from collections.abc import AsyncIterator
from uuid import UUID

import redis.asyncio as aioredis

from ..config import settings
from . import agent_auth, agent_service, memory_service, prompts, sprite_service
from . import harness as harness_mod

logger = logging.getLogger(__name__)

# Agent name stamped on chat history events — shows up in Sessions "By agent".
AGENT_NAME = "Stash Agent"

# Reseeded turns replay at most this many stored turns into the fresh prompt.
_RESEED_MAX_TURNS = 40
_RESEED_MAX_CHARS = 24_000

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL)
    return _redis


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _redact(text: str, provider_env: dict[str, str]) -> str:
    """Strip the injected provider key (and sk-ant-shaped tokens) from output —
    a failed command echoes its env prefix."""
    for value in provider_env.values():
        if value:
            text = text.replace(value, "[redacted]")
    return re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[redacted]", text)


async def _load_history(
    owner_user_id: UUID, session_id: str, user_id: UUID, limit: int | None = None
) -> list[dict]:
    """Rebuild the [{role, content}] conversation from stored session events."""
    events = await memory_service.read_session_events(owner_user_id, session_id, user_id)
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


def _reseed_prompt(history: list[dict], message: str) -> str:
    """The current message prefixed with stored history, for turns where the
    on-box transcript is gone and the session starts fresh."""
    lines = [f"{turn['role']}: {turn['content']}" for turn in history[-_RESEED_MAX_TURNS:]]
    replay = "\n\n".join(lines)[-_RESEED_MAX_CHARS:]
    return (
        "Context: this conversation continues from an earlier session. "
        "Prior turns, oldest first:\n\n"
        f"{replay}\n\n---\n\n{message}"
    )


async def _run_harness(
    harness: harness_mod.Harness,
    sprite: sprite_service.Sprite,
    argv: list[str],
    state: harness_mod.TurnState,
    provider_env: dict[str, str],
) -> AsyncIterator[dict]:
    """Exec one harness turn on the box; yields contract events. Sets
    state.error / state.resume_missing on failure instead of raising, so the
    caller decides between reseed and surfacing the error."""
    stdout_decoder = codecs.getincrementaldecoder("utf-8")("replace")
    buffer = ""
    exit_code: int | None = None

    # The open exec stream itself keeps the sprite awake — Sprites only sleeps
    # after activity stops, and a live connection is activity. stderr merges
    # into stdout on Sprites, so we parse everything from the stdout stream.
    async for event in sprite_service.exec_stream(
        sprite, argv, env=provider_env, cwd=sprite_service.SPRITE_WORKDIR
    ):
        if "exit_code" in event:
            exit_code = event["exit_code"]
            break
        buffer += stdout_decoder.decode(event["data"])
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.strip():
                for mapped in harness_mod.map_line(harness, line, state):
                    yield _redact_event(mapped, provider_env)
    if buffer.strip():
        for mapped in harness_mod.map_line(harness, buffer, state):
            yield _redact_event(mapped, provider_env)

    if exit_code != 0 and state.error is None and not state.resume_missing:
        state.error = f"agent exited with code {exit_code}"
    if state.error and harness_mod.RESUME_MISSING_RE.search(state.error):
        state.resume_missing = True


def _redact_event(event: dict, provider_env: dict[str, str]) -> dict:
    if event.get("type") == "text":
        event["delta"] = _redact(event["delta"], provider_env)
    return event


def _tool_event_summary(event: dict) -> tuple[str, dict]:
    """A compact tool_use content + metadata, matching the local plugin's
    format so cloud and local session transcripts render the same way."""
    name = event.get("name") or "tool"
    args = event.get("args") or {}
    if name == "Bash" and args.get("command"):
        command = str(args["command"])[:300]
        return f"Ran: {command}", {"command": command}
    if name in ("Edit", "Write") and args.get("file_path"):
        return f"{'Edited' if name == 'Edit' else 'Created/wrote'} {args['file_path']}", {
            "file_path": args["file_path"]
        }
    if name == "Read" and args.get("file_path"):
        return f"Read {args['file_path']}", {"file_path": args["file_path"]}
    preview = json.dumps(args)[:300]
    return f"{name}: {preview}", {"args_preview": preview}


async def _record_tool_event(
    owner_user_id: UUID, user_id: UUID, session_id: str, event: dict, provider_env: dict[str, str]
) -> None:
    """Persist a harness tool call as a history event. Cloud runs have no
    plugin hooks streaming these, so without this the stored session is just
    prompt + final answer — unauditable."""
    content, metadata = _tool_event_summary(event)
    await memory_service.push_event(
        owner_user_id,
        AGENT_NAME,
        "tool_use",
        _redact(content, provider_env),
        user_id,
        session_id=session_id,
        tool_name=event.get("name") or "tool",
        metadata=metadata,
    )


async def _turn_events(
    auth: agent_auth.RunAuth,
    sprite: sprite_service.Sprite,
    history: list[dict],
    message: str,
    session_id: str,
    system_prompt: str,
    disallowed_tools: list[str] | None = None,
) -> AsyncIterator[dict]:
    """One full agent turn: resume the harness session, reseeding from stored
    history if the box has lost it. Ends with exactly one end/error event."""
    harness = auth.harness
    provider_env = auth.env
    # OAuth harnesses read a credential file, not an env var — write it first.
    for path, contents in auth.files.items():
        await sprite_service.write_file(sprite, path, contents)

    native_id = await harness_mod.get_native_id(session_id, harness.id)
    key = harness_mod.session_key(harness, session_id, native_id)
    # Claude resumes when the conversation has prior turns (its id is
    # deterministic); the others resume only once they've minted a native id.
    if harness is harness_mod.CLAUDE:
        resume = any(t["role"] == "assistant" for t in history)
    else:
        resume = native_id is not None

    state = harness_mod.TurnState()
    argv = harness_mod.build_argv(
        harness,
        message,
        session_key=key,
        resume=resume,
        system_prompt=system_prompt,
        disallowed_tools=disallowed_tools,
    )
    async for event in _run_harness(harness, sprite, argv, state, provider_env):
        yield event

    if state.resume_missing:
        # Cattle rule: the on-box transcript is gone. Recreate the canonical
        # session fresh (Claude: --session-id <same key>) with history seeded
        # into the prompt, so later turns resume it normally again.
        logger.warning(
            "cloud agent: transcript missing for %s — reseeding from history", session_id
        )
        state = harness_mod.TurnState()
        argv = harness_mod.build_argv(
            harness,
            _reseed_prompt(history, message),
            session_key=key,
            resume=False,
            system_prompt=system_prompt,
            disallowed_tools=disallowed_tools,
        )
        async for event in _run_harness(harness, sprite, argv, state, provider_env):
            yield event

    if state.native_id:
        await harness_mod.set_native_id(session_id, harness.id, state.native_id)

    if state.error is not None:
        yield {"type": "error", "message": state.error}
    yield {"type": "end", "_result_text": state.result_text or ""}


class TurnInProgress(RuntimeError):
    """Another turn is already running in this session."""


class _TurnLock:
    def __init__(self, session_id: str) -> None:
        self._key = f"agent-turn:{session_id}"
        self._token = secrets.token_hex(16)

    async def __aenter__(self) -> None:
        acquired = await _get_redis().set(
            self._key, self._token, nx=True, ex=settings.AGENT_TURN_TIMEOUT_SECONDS
        )
        if not acquired:
            raise TurnInProgress

    async def __aexit__(self, *exc) -> None:
        r = _get_redis()
        if await r.get(self._key) == self._token.encode():
            await r.delete(self._key)


def _system_prompt(owner_name: str, persona: str | None) -> str:
    base = prompts.render_sprite_system(owner_name)
    return f"{base}\n\n{persona}" if persona else base


async def build_scheduled_turn(agent: dict, run_stamp: str) -> tuple[str, str]:
    """(session_id, message) for one run of a scheduled agent.

    The reserved Memory curator (is_curator) runs the curation prompt built
    server-side from its watermark; other scheduled agents run schedule_prompt.
    Each run gets its own per-run session id so history (and the CLI transcript
    it replays) can't grow unbounded across a long-lived schedule."""
    from . import files_tree_service, prompts

    user_id = UUID(str(agent["user_id"]))
    if agent.get("is_curator"):
        memory = await files_tree_service.get_or_create_memory_folder(user_id, user_id)
        since = agent["curated_through"].isoformat() if agent.get("curated_through") else None
        message = prompts.render_curator_prompt(memory["id"], since)
        return f"agent-curate-{agent['id']}-{run_stamp}", message
    return f"agent-sched-{agent['id']}-{run_stamp}", agent["schedule_prompt"]


async def run_scheduled(agent: dict, run_stamp: str) -> str:
    """Run a scheduled agent headless — one turn into a fresh per-run session —
    and return the result text."""
    from . import user_service

    user_id = UUID(str(agent["user_id"]))
    user = await user_service.get_user_by_id(user_id)
    if user is None:
        return ""
    owner_name = user["display_name"] or user["name"]

    session_id, message = await build_scheduled_turn(agent, run_stamp)
    return await run_chat(
        user_id,
        owner_name,
        user_id,
        session_id,
        message,
        model_provider=agent["model_provider"],
        persona=agent["system_prompt"],
    )


async def stream_chat(
    owner_user_id: UUID,
    owner_name: str,
    user_id: UUID,
    session_id: str,
    message: str,
    auth: agent_auth.RunAuth,
    persona: str | None = None,
) -> AsyncIterator[str]:
    """Multi-turn agent chat over a stored session, streamed as SSE.

    `auth` is the harness + credentials resolved (and gated) by the router
    before the stream started, so a 402 is a clean HTTP error, not an SSE one.
    `persona` is the selected agent's extra system prompt.
    """
    try:
        async with _TurnLock(session_id):
            history = await _load_history(owner_user_id, session_id, user_id)
            await memory_service.push_event(
                owner_user_id, AGENT_NAME, "user_message", message, user_id, session_id=session_id
            )
            yield _sse({"type": "session", "session_id": session_id})
            yield _sse({"type": "status", "stage": "waking"})

            acquire = asyncio.create_task(sprite_service.acquire(user_id))
            while not acquire.done():
                # SSE comment keepalives while a first-ever provision runs.
                yield ": ping\n\n"
                await asyncio.wait({acquire}, timeout=10)
            sprite = acquire.result()
            await sprite_service.touch(user_id)

            final = ""
            async for event in _turn_events(
                auth,
                sprite,
                history,
                message,
                session_id,
                _system_prompt(owner_name, persona),
            ):
                if event["type"] == "end":
                    final = event.pop("_result_text")
                elif event["type"] == "tool":
                    await _record_tool_event(owner_user_id, user_id, session_id, event, auth.env)
                yield _sse(event)

            if final:
                await memory_service.push_event(
                    owner_user_id,
                    AGENT_NAME,
                    "assistant_message",
                    final,
                    user_id,
                    session_id=session_id,
                )
    except TurnInProgress:
        yield _sse({"type": "error", "message": "A turn is already running in this chat."})
        yield _sse({"type": "end"})
    except Exception:
        # SSE has already started, so an exception can't become an HTTP error —
        # without this the stream just dies and the client sees nothing.
        logger.exception("cloud agent: turn failed for session %s", session_id)
        yield _sse({"type": "error", "message": "The agent turn failed. Try again."})
        yield _sse({"type": "end"})


# Slack messages are an untrusted surface: strip the harness's own mutating
# tools so a prompt-injected message can't edit the box or the Stash through
# them. (The stash CLI via Bash remains — hardening tracked as follow-up.)
SLACK_DISALLOWED_TOOLS = ["Write", "Edit", "NotebookEdit", "Bash(rm:*)"]


class NeedsAuth(Exception):
    """Surfaced to a channel (Slack/Telegram) so it can prompt the user to
    connect a key or upgrade, instead of failing silently."""


async def run_chat(
    owner_user_id: UUID,
    owner_name: str,
    user_id: UUID,
    session_id: str,
    message: str,
    channel: str | None = None,
    model_provider: str | None = None,
    persona: str | None = None,
) -> str:
    """Non-streaming turn for Slack/Telegram/scheduled: returns the final answer.
    `channel` ('slack'|'telegram') selects the bound agent's model + persona;
    a scheduled run passes model_provider/persona directly.
    Raises NeedsAuth for an unconnected free account so the channel can prompt."""
    if channel:
        agent = await agent_service.channel_agent(user_id, channel)
        model_provider = agent["model_provider"]
        persona = agent["system_prompt"]
    try:
        auth = await agent_auth.resolve(user_id, model_provider)
    except agent_auth.NeedsAuth:
        raise NeedsAuth
    except agent_auth.ProviderNotConfigured:
        raise RuntimeError("cloud agent is not configured")
    async with _TurnLock(session_id):
        history = await _load_history(owner_user_id, session_id, user_id)
        await memory_service.push_event(
            owner_user_id, AGENT_NAME, "user_message", message, user_id, session_id=session_id
        )
        sprite = await sprite_service.acquire(user_id)
        await sprite_service.touch(user_id)

        final = ""
        error: str | None = None
        async for event in _turn_events(
            auth,
            sprite,
            history,
            message,
            session_id,
            _system_prompt(owner_name, persona),
            # Channel messages are untrusted input; scheduled runs (curator
            # included) execute a trusted prompt and need their full toolset.
            disallowed_tools=SLACK_DISALLOWED_TOOLS if channel else None,
        ):
            if event["type"] == "end":
                final = event.pop("_result_text")
            elif event["type"] == "error":
                error = event["message"]
            elif event["type"] == "tool":
                await _record_tool_event(owner_user_id, user_id, session_id, event, auth.env)
        if error:
            raise RuntimeError(f"agent turn failed: {error}")

        if final:
            await memory_service.push_event(
                owner_user_id,
                AGENT_NAME,
                "assistant_message",
                final,
                user_id,
                session_id=session_id,
            )
        return final
