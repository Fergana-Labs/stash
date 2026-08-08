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
import contextlib
import json
import logging
import re
import secrets
import shutil
from collections.abc import AsyncIterator
from uuid import UUID

import redis.asyncio as aioredis

from ..config import settings
from . import agent_auth, agent_service, mcp_server_service, memory_service, prompts, sprite_service
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
        # The cause is in the CLI's plain-text output (auth failures, missing
        # binaries, crashes) — without it this error is undebuggable.
        tail = _redact(" ".join(state.unparsed), provider_env)[-400:]
        if tail:
            state.error += f": {tail}"
    if state.error:
        # Harness-emitted errors can carry raw request/response fragments
        # (the mappers now preserve them) — scrub the injected key like the
        # plain-text tail above.
        state.error = _redact(state.error, provider_env)
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
    owner_user_id: UUID,
    user_id: UUID,
    session_id: str,
    event: dict,
    provider_env: dict[str, str],
    agent_name: str,
) -> None:
    """Persist a harness tool call as a history event. Cloud runs have no
    plugin hooks streaming these, so without this the stored session is just
    prompt + final answer — unauditable."""
    content, metadata = _tool_event_summary(event)
    await memory_service.push_event(
        owner_user_id,
        agent_name,
        "tool_use",
        _redact(content, provider_env),
        user_id,
        session_id=session_id,
        tool_name=event.get("name") or "tool",
        metadata=metadata,
    )


# Stored marker for a failed run's closing message — the runs API reads it back
# to flag the run, so the client never string-matches message text itself.
RUN_FAILED_PREFIX = "⚠️ Agent run failed:"


async def _record_run_failure(
    owner_user_id: UUID, user_id: UUID, session_id: str, agent_name: str, error: str
) -> None:
    """Close a failed turn's stored session with the error. Without this a
    crashed run leaves a prompt with no reply — indistinguishable from a run
    that never happened."""
    await memory_service.push_event(
        owner_user_id,
        agent_name,
        "assistant_message",
        f"{RUN_FAILED_PREFIX} {error}",
        user_id,
        session_id=session_id,
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


class TurnStopped(Exception):
    """The user requested this turn stop mid-run."""


# The note recorded (and streamed) when a turn is stopped mid-run.
STOPPED_NOTE = "⏹ Stopped by user."

_STOP_POLL_SECONDS = 2


def _stop_key(session_id: str) -> str:
    return f"agent-turn-stop:{session_id}"


async def turn_running(session_id: str) -> bool:
    return await _get_redis().get(f"agent-turn:{session_id}") is not None


async def request_stop(session_id: str) -> bool:
    """Flag the session's running turn to stop. False when no turn is running."""
    r = _get_redis()
    if await r.get(f"agent-turn:{session_id}") is None:
        return False
    await r.set(_stop_key(session_id), "1", ex=settings.AGENT_TURN_TIMEOUT_SECONDS)
    return True


async def _stoppable(events: AsyncIterator[dict], session_id: str) -> AsyncIterator[dict]:
    """Yield turn events until the session's stop flag appears in redis.

    Closing the inner generator kills the harness exec (local mode kills the
    subprocess; Sprites mode closes the exec websocket), so a stop ends the
    run on the box, not just this stream."""
    r = _get_redis()
    key = _stop_key(session_id)
    # A stop requested after the previous turn ended must not kill this one.
    await r.delete(key)
    iterator = aiter(events)
    try:
        while True:
            next_event = asyncio.ensure_future(anext(iterator))
            while not next_event.done():
                await asyncio.wait({next_event}, timeout=_STOP_POLL_SECONDS)
                if not next_event.done() and await r.get(key) is not None:
                    next_event.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await next_event
                    raise TurnStopped
            try:
                event = next_event.result()
            except StopAsyncIteration:
                return
            yield event
    finally:
        await r.delete(key)
        await iterator.aclose()


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


def scheduled_session_prefix(agent: dict) -> str:
    """Prefix of every per-run session id build_scheduled_turn mints for this
    agent — the runs API groups stored history by it."""
    kind = "curate" if agent.get("is_curator") else "sched"
    return f"agent-{kind}-{agent['id']}-"


async def build_scheduled_turn(agent: dict, run_stamp: str) -> tuple[str, str]:
    """(session_id, message) for one run of a scheduled agent.

    The reserved Memory curator (is_curator) runs the curation prompt built
    server-side from its watermark; other scheduled agents run schedule_prompt.
    Each run gets its own per-run session id so history (and the CLI transcript
    it replays) can't grow unbounded across a long-lived schedule."""
    from . import files_tree_service, prompts

    user_id = UUID(str(agent["user_id"]))
    session_id = f"{scheduled_session_prefix(agent)}{run_stamp}"
    if agent.get("is_curator"):
        memory = await files_tree_service.get_or_create_memory_folder(user_id, user_id)
        since = agent["curated_through"].isoformat() if agent.get("curated_through") else None
        return session_id, prompts.render_curator_prompt(memory["id"], since)
    return session_id, agent["schedule_prompt"]


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
        agent_name=agent["name"],
    )


# Detached turn tasks need a strong reference until they finish — asyncio
# holds only weak refs, and a GC'd task is a silently killed turn.
_detached_turns: set[asyncio.Task] = set()

_TURN_DONE = object()


async def _pump_turn(
    queue: asyncio.Queue,
    owner_user_id: UUID,
    owner_name: str,
    user_id: UUID,
    session_id: str,
    message: str,
    auth: agent_auth.RunAuth,
    persona: str | None,
    agent_name: str,
) -> None:
    """One chat turn, decoupled from its viewer.

    Events go to `queue`, but execution, recording, and the turn lock never
    depend on anyone reading them: the sandboxed turn is the real work and
    must survive a closed tab — the stream is only a live view of it."""

    def put(event: dict) -> None:
        queue.put_nowait(event)

    try:
        async with _TurnLock(session_id):
            history = await _load_history(owner_user_id, session_id, user_id)
            await memory_service.push_event(
                owner_user_id, agent_name, "user_message", message, user_id, session_id=session_id
            )
            put({"type": "session", "session_id": session_id})
            put({"type": "status", "stage": "waking"})

            sprite = await sprite_service.acquire(user_id)
            await sprite_service.touch(user_id)
            # Registered MCP servers reach the harness via the workdir's
            # .mcp.json, rewritten every turn so removals propagate too.
            await mcp_server_service.sync_sprite_config(user_id, sprite)

            final = ""
            error: str | None = None
            turn = _turn_events(
                auth,
                sprite,
                history,
                message,
                session_id,
                _system_prompt(owner_name, persona),
            )
            try:
                async for event in _stoppable(turn, session_id):
                    if event["type"] == "end":
                        final = event.pop("_result_text")
                    elif event["type"] == "error":
                        error = event["message"]
                    elif event["type"] == "tool":
                        await _record_tool_event(
                            owner_user_id, user_id, session_id, event, auth.env, agent_name
                        )
                    put(event)
            except TurnStopped:
                final = STOPPED_NOTE
                put({"type": "text", "delta": STOPPED_NOTE})
                put({"type": "end"})

            if final:
                await memory_service.push_event(
                    owner_user_id,
                    agent_name,
                    "assistant_message",
                    final,
                    user_id,
                    session_id=session_id,
                )
            elif error:
                await _record_run_failure(owner_user_id, user_id, session_id, agent_name, error)
    except TurnInProgress:
        put({"type": "error", "message": "A turn is already running in this chat."})
        put({"type": "end"})
    except Exception:
        # The client may be long gone, so the log is the only reliable trace.
        logger.exception("cloud agent: turn failed for session %s", session_id)
        try:
            await _record_run_failure(
                owner_user_id, user_id, session_id, agent_name, "The agent turn failed."
            )
        except Exception:
            # Recording is best-effort here — the client must still get its
            # error + end events even if the DB write is what's broken.
            logger.exception("cloud agent: could not record failure for %s", session_id)
        put({"type": "error", "message": "The agent turn failed. Try again."})
        put({"type": "end"})
    finally:
        queue.put_nowait(_TURN_DONE)


async def stream_chat(
    owner_user_id: UUID,
    owner_name: str,
    user_id: UUID,
    session_id: str,
    message: str,
    auth: agent_auth.RunAuth,
    persona: str | None = None,
    agent_name: str = AGENT_NAME,
) -> AsyncIterator[str]:
    """Multi-turn agent chat over a stored session, streamed as SSE.

    `auth` is the harness + credentials resolved (and gated) by the router
    before the stream started, so a 402 is a clean HTTP error, not an SSE one.
    `persona` is the selected agent's extra system prompt.

    The turn itself runs as a detached task (_pump_turn): a dropped stream —
    closed tab, in-app navigation — never cancels it, the reply is still
    recorded into the session, and the turn lock still releases. A returning
    client reloads the stored session and polls the status endpoint."""
    queue: asyncio.Queue = asyncio.Queue()
    turn = asyncio.create_task(
        _pump_turn(
            queue,
            owner_user_id,
            owner_name,
            user_id,
            session_id,
            message,
            auth,
            persona,
            agent_name,
        )
    )
    _detached_turns.add(turn)
    turn.add_done_callback(_detached_turns.discard)
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=10)
        except TimeoutError:
            # SSE comment keepalive through provisioning waits and long tool calls.
            yield ": ping\n\n"
            continue
        if event is _TURN_DONE:
            return
        yield _sse(event)


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
    agent_name: str = AGENT_NAME,
) -> str:
    """Non-streaming turn for Slack/Telegram/scheduled: returns the final answer.
    `channel` ('slack'|'telegram') selects the bound agent's model + persona;
    a scheduled run passes model_provider/persona directly.
    Raises NeedsAuth for an unconnected free account so the channel can prompt."""
    if channel:
        agent = await agent_service.channel_agent(user_id, channel)
        model_provider = agent["model_provider"]
        persona = agent["system_prompt"]
        agent_name = agent["name"]
    try:
        auth = await agent_auth.resolve(user_id, model_provider)
    except agent_auth.NeedsAuth:
        raise NeedsAuth
    except agent_auth.ProviderNotConfigured:
        raise RuntimeError("cloud agent is not configured")
    # Fail loud before spawning: a missing CLI produces a cryptic FileNotFoundError
    # deep in asyncio that doesn't tell the operator what to install.
    if not shutil.which(auth.harness.bin):
        raise RuntimeError(
            f"agent CLI '{auth.harness.bin}' not found on PATH — "
            f"install it on the worker host so the agent can run turns"
        )
    async with _TurnLock(session_id):
        history = await _load_history(owner_user_id, session_id, user_id)
        await memory_service.push_event(
            owner_user_id, agent_name, "user_message", message, user_id, session_id=session_id
        )
        sprite = await sprite_service.acquire(user_id)
        await sprite_service.touch(user_id)
        # Registered MCP servers reach the harness via the workdir's
        # .mcp.json, rewritten every turn so removals propagate too.
        await mcp_server_service.sync_sprite_config(user_id, sprite)

        final = ""
        error: str | None = None
        cause: Exception | None = None
        turn = _turn_events(
            auth,
            sprite,
            history,
            message,
            session_id,
            _system_prompt(owner_name, persona),
            # Channel messages are untrusted input; scheduled runs (curator
            # included) execute a trusted prompt and need their full toolset.
            disallowed_tools=SLACK_DISALLOWED_TOOLS if channel else None,
        )
        try:
            async for event in _stoppable(turn, session_id):
                if event["type"] == "end":
                    final = event.pop("_result_text")
                elif event["type"] == "error":
                    error = event["message"]
                elif event["type"] == "tool":
                    await _record_tool_event(
                        owner_user_id, user_id, session_id, event, auth.env, agent_name
                    )
        except TurnStopped:
            final = STOPPED_NOTE
        except Exception as e:
            # Substrate-level failures (exec crash, sprite gone) — record them
            # like harness errors so the stored session isn't a dangling prompt.
            error, cause = str(e), e
        if error:
            await _record_run_failure(owner_user_id, user_id, session_id, agent_name, error)
            raise RuntimeError(f"agent turn failed: {error}") from cause

        if final:
            await memory_service.push_event(
                owner_user_id,
                agent_name,
                "assistant_message",
                final,
                user_id,
                session_id=session_id,
            )
        return final
