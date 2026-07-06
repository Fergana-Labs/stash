"""The Stash agent, running as Claude Code on the user's cloud computer.

Replaces the in-process tool loop for web chat and Slack: each turn execs
`claude -p … --output-format stream-json` on the user's sprite (see
sprite_service) and maps the CLI's stream-json events onto the existing
event contract ({text, tool, tool_result, end} plus new {status, error})
that the web ChatPanel and Slack already consume.

Conversation state:
  - history_events in Postgres is the source of truth (a chat is a Session).
  - Claude Code's on-box transcript enables --resume between turns; if it's
    gone (recreated sprite, restored checkpoint), the turn reseeds a fresh
    CLI session from stored history — the box is cattle, the DB is not.
"""

from __future__ import annotations

import asyncio
import codecs
import json
import logging
import re
import secrets
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import redis.asyncio as aioredis

from ..config import settings
from . import memory_service, prompts, sprite_service

logger = logging.getLogger(__name__)

# Agent name stamped on chat history events — shows up in Sessions "By agent".
AGENT_NAME = "Stash Agent"

# The CLI's complaint when --resume points at a transcript this box has
# never seen. Triggers the reseed-from-history path (and nothing else does).
_RESUME_MISSING_RE = re.compile(r"no conversation found", re.IGNORECASE)

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


def _claude_session_uuid(session_id: str) -> str:
    """Deterministic CLI session id per Stash session, so every turn of a chat
    resumes the same on-box transcript."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"stash-agent:{session_id}"))


def _redact(text: str) -> str:
    if settings.ANTHROPIC_API_KEY:
        text = text.replace(settings.ANTHROPIC_API_KEY, "[redacted]")
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
    on-box transcript is gone and the CLI session starts fresh."""
    lines: list[str] = []
    for turn in history[-_RESEED_MAX_TURNS:]:
        lines.append(f"{turn['role']}: {turn['content']}")
    replay = "\n\n".join(lines)[-_RESEED_MAX_CHARS:]
    return (
        "Context: this conversation continues from an earlier session. "
        "Prior turns, oldest first:\n\n"
        f"{replay}\n\n---\n\n{message}"
    )


def _claude_argv(
    prompt: str,
    session_uuid: str,
    *,
    resume: bool,
    system_prompt: str,
    disallowed_tools: list[str] | None = None,
) -> list[str]:
    argv = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--resume" if resume else "--session-id",
        session_uuid,
        "--append-system-prompt",
        system_prompt,
        "--dangerously-skip-permissions",
    ]
    if disallowed_tools:
        argv += ["--disallowedTools", ",".join(disallowed_tools)]
    return argv


def _turn_env() -> dict[str, str]:
    # Local dev mode runs this machine's own claude install, which brings its
    # own login — no key injection. On sprites, the backend's key is the only
    # auth the box has.
    if settings.AGENT_EXEC_MODE == "local":
        return {}
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return {
        "ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY,
        "ANTHROPIC_MODEL": settings.ANTHROPIC_MODEL,
    }


class _TurnState:
    """Per-turn bookkeeping while mapping the CLI's stream-json events."""

    def __init__(self) -> None:
        self.tool_names: dict[str, str] = {}
        self.result_text: str | None = None
        self.error: str | None = None
        self.resume_missing = False


def _map_line(line: str, state: _TurnState) -> list[dict]:
    """One stream-json stdout line → zero or more contract events."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        # Sprites merges stderr into the stdout stream, so CLI warnings land
        # here. Skip them, but still catch the "resume points at a transcript
        # this box never had" signal so the turn can reseed from history.
        if _RESUME_MISSING_RE.search(line):
            state.resume_missing = True
        logger.warning("cloud agent: non-JSON stdout line: %.200s", line)
        return []

    kind = obj.get("type")
    if kind == "stream_event":
        event = obj.get("event") or {}
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                return [{"type": "text", "delta": _redact(delta["text"])}]
        return []

    if kind == "assistant":
        events = []
        for block in (obj.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use":
                state.tool_names[block["id"]] = block["name"]
                events.append(
                    {
                        "type": "tool",
                        "id": block["id"],
                        "name": block["name"],
                        "args": block.get("input") or {},
                    }
                )
        return events

    if kind == "user":
        events = []
        for block in (obj.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tool_id = block.get("tool_use_id") or ""
                events.append(
                    {
                        "type": "tool_result",
                        "id": tool_id,
                        "name": state.tool_names.get(tool_id, ""),
                        "ok": not block.get("is_error", False),
                    }
                )
        return events

    if kind == "result":
        # The CLI can report subtype "success" with is_error=true (e.g. a
        # rejected API key) — is_error is the authoritative bit.
        if obj.get("subtype") == "success" and not obj.get("is_error"):
            state.result_text = (obj.get("result") or "").strip()
        else:
            state.error = _redact(str(obj.get("result") or obj.get("subtype") or "unknown error"))
        return []

    return []  # system:init and friends


async def _run_claude(
    sprite: sprite_service.Sprite,
    argv: list[str],
    state: _TurnState,
) -> AsyncIterator[dict]:
    """Exec one claude turn on the box; yields contract events. Sets
    state.error / state.resume_missing on failure instead of raising, so the
    caller decides between reseed and surfacing the error."""
    stdout_decoder = codecs.getincrementaldecoder("utf-8")("replace")
    stderr_tail: list[str] = []
    buffer = ""
    exit_code: int | None = None

    # The open exec stream itself keeps the sprite awake — Sprites only sleeps
    # after activity stops, and a live connection is activity.
    async for event in sprite_service.exec_stream(
        sprite, argv, env=_turn_env(), cwd=sprite_service.SPRITE_WORKDIR
    ):
        if "exit_code" in event:
            exit_code = event["exit_code"]
            break
        if event["stream"] == "stderr":
            stderr_tail.append(event["data"].decode("utf-8", "replace"))
            stderr_tail = stderr_tail[-50:]
            continue
        buffer += stdout_decoder.decode(event["data"])
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.strip():
                for mapped in _map_line(line, state):
                    yield mapped
    if buffer.strip():
        for mapped in _map_line(buffer, state):
            yield mapped

    if exit_code != 0 and state.error is None:
        stderr_text = _redact("".join(stderr_tail).strip())
        if _RESUME_MISSING_RE.search(stderr_text):
            state.resume_missing = True
        else:
            state.error = stderr_text[-2000:] or f"agent exited with code {exit_code}"
    elif state.error and _RESUME_MISSING_RE.search(state.error):
        state.resume_missing = True


async def _turn_events(
    sprite: sprite_service.Sprite,
    history: list[dict],
    message: str,
    session_id: str,
    system_prompt: str,
    disallowed_tools: list[str] | None = None,
) -> AsyncIterator[dict]:
    """One full agent turn: resume the CLI session, reseeding from stored
    history if the box has lost it. Ends with exactly one end/error event."""
    session_uuid = _claude_session_uuid(session_id)
    resume = any(t["role"] == "assistant" for t in history)

    state = _TurnState()
    argv = _claude_argv(
        message,
        session_uuid,
        resume=resume,
        system_prompt=system_prompt,
        disallowed_tools=disallowed_tools,
    )
    async for event in _run_claude(sprite, argv, state):
        yield event

    if state.resume_missing:
        # Cattle rule: the on-box transcript is gone; rebuild from the DB.
        logger.warning("cloud agent: transcript missing for %s — reseeding from history", session_id)
        state = _TurnState()
        argv = _claude_argv(
            _reseed_prompt(history, message),
            str(uuid.uuid4()),
            resume=False,
            system_prompt=system_prompt,
            disallowed_tools=disallowed_tools,
        )
        async for event in _run_claude(sprite, argv, state):
            yield event

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


async def stream_chat(
    owner_user_id: UUID,
    owner_name: str,
    user_id: UUID,
    session_id: str,
    message: str,
) -> AsyncIterator[str]:
    """Multi-turn agent chat over a stored session, streamed as SSE."""
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
                sprite, history, message, session_id, prompts.render_sprite_system(owner_name)
            ):
                if event["type"] == "end":
                    final = event.pop("_result_text")
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


async def run_chat(
    owner_user_id: UUID,
    owner_name: str,
    user_id: UUID,
    session_id: str,
    message: str,
) -> str:
    """Non-streaming turn for Slack: returns the final answer text."""
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
            sprite,
            history,
            message,
            session_id,
            prompts.render_sprite_system(owner_name),
            disallowed_tools=SLACK_DISALLOWED_TOOLS,
        ):
            if event["type"] == "end":
                final = event.pop("_result_text")
            elif event["type"] == "error":
                error = event["message"]
        if error:
            raise RuntimeError(f"agent turn failed: {error}")

        if final:
            await memory_service.push_event(
                owner_user_id, AGENT_NAME, "assistant_message", final, user_id, session_id=session_id
            )
        return final
