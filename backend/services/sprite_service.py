"""Per-user cloud computers — the substrate seam over Fly Sprites.

Each user gets one persistent sprite VM (sprites.dev): durable disk,
auto-sleep when idle, wakes on the next request. The agent brain
(sprite_agent_service) talks to the box only through this module, so a
later port to self-managed VMs swaps this file, nothing else.

Two exec modes, chosen once by AGENT_EXEC_MODE:
  - "sprites": REST + WebSocket exec against api.sprites.dev.
  - "local":   subprocess on this machine's own claude install (dev mode).

Commands are argv lists end to end — no shell string assembly, no quoting
bugs. The Sprites exec API's `env` parameter REPLACES the default
environment, so sprites-mode execs always pass a complete environment.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

import httpx
import websockets

from .. import auth
from ..config import settings
from ..database import get_pool
from . import prompts

# The sprite runs as root (Sprites boxes are single-user, root-access VMs).
SPRITE_HOME = "/root"
SPRITE_WORKDIR = f"{SPRITE_HOME}/work"
SPRITE_PATH = f"{SPRITE_HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin"

# A first-ever provision creates the VM and seeds it (~10-30s).
PROVISION_TIMEOUT_S = 180
# A provisioning row older than this is presumed crashed and retried.
STALE_PROVISION_S = 300

# Binary WSS exec frames are tagged by their first byte.
_FRAME_STDOUT = 0x01
_FRAME_STDERR = 0x02
_FRAME_EXIT = 0x03


class SpriteError(RuntimeError):
    """A sprite operation failed (API error, seed failure, exec failure)."""


@dataclass(frozen=True)
class Sprite:
    name: str


def _sprite_name(user_id: UUID) -> str:
    return f"stash-u-{user_id.hex}"


# ---------------------------------------------------------------------------
# Acquire / provision
# ---------------------------------------------------------------------------


async def acquire(user_id: UUID) -> Sprite:
    """The user's sprite, provisioning it on first use.

    Wake is implicit — exec'ing against a sleeping sprite wakes it.
    """
    if settings.AGENT_EXEC_MODE == "local":
        _local_workdir().mkdir(parents=True, exist_ok=True)
        return Sprite(name="local")

    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT sprite_name, status FROM user_sprites WHERE user_id = $1", user_id
    )
    if row and row["status"] == "ready":
        return Sprite(name=row["sprite_name"])
    return await _provision(user_id)


async def _provision(user_id: UUID) -> Sprite:
    """Create + seed the user's sprite exactly once.

    The 'provisioning' row is the concurrency lock: whoever inserts it does
    the work; everyone else polls until it flips to 'ready'. Rows stuck in
    'provisioning' past STALE_PROVISION_S are presumed crashed and retaken.
    """
    pool = get_pool()
    name = _sprite_name(user_id)

    won = await pool.fetchrow(
        """
        INSERT INTO user_sprites (user_id, sprite_name, status)
        VALUES ($1, $2, 'provisioning')
        ON CONFLICT (user_id) DO UPDATE
            SET status = 'provisioning', created_at = now()
            WHERE user_sprites.status = 'provisioning'
              AND user_sprites.created_at < now() - make_interval(secs => $3)
        RETURNING user_id
        """,
        user_id,
        name,
        STALE_PROVISION_S,
    )
    if won is None:
        return await _wait_until_ready(user_id)

    try:
        stash_key = await auth.create_api_key(user_id, name="cloud computer", key_type="machine")
        await _sprites_api("POST", "/v1/sprites", json={"name": name})
        sprite = Sprite(name=name)
        output, code = await exec_collect(
            sprite,
            ["bash", "-c", _seed_script(stash_key)],
            env={},
            timeout_s=PROVISION_TIMEOUT_S,
        )
        if code != 0:
            raise SpriteError(f"sprite seed script exited {code}: {output[-2000:]}")
        await _register_skills_sync_service(sprite)
    except BaseException:
        # Fail loud and leave nothing half-made: the sprite (if created) and
        # the row both go, so the next attempt starts clean.
        with contextlib.suppress(httpx.HTTPError, SpriteError):
            await _sprites_api("DELETE", f"/v1/sprites/{name}")
        await pool.execute("DELETE FROM user_sprites WHERE user_id = $1", user_id)
        raise

    await pool.execute(
        "UPDATE user_sprites SET status = 'ready', last_active_at = now() WHERE user_id = $1",
        user_id,
    )
    return sprite


async def _wait_until_ready(user_id: UUID) -> Sprite:
    """Another request is provisioning this user's sprite; wait for it."""
    pool = get_pool()
    deadline = asyncio.get_event_loop().time() + PROVISION_TIMEOUT_S
    while asyncio.get_event_loop().time() < deadline:
        row = await pool.fetchrow(
            "SELECT sprite_name, status FROM user_sprites WHERE user_id = $1", user_id
        )
        if row is None:
            raise SpriteError("sprite provisioning failed in a concurrent request")
        if row["status"] == "ready":
            return Sprite(name=row["sprite_name"])
        await asyncio.sleep(1)
    raise SpriteError("timed out waiting for sprite provisioning")


def _seed_script(stash_key: str) -> str:
    """Idempotent first-boot setup: stash CLI, headless auth, the Claude Code
    plugin (session upload), skills, and the workspace."""
    config = json.dumps(
        {"base_url": settings.SPRITES_STASH_API_URL, "api_key": stash_key, "username": ""}
    )
    claude_md = prompts.render_sprite_workspace_claude_md()
    return f"""
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
command -v stash > /dev/null || python3 -m pip install --user --break-system-packages stashai
mkdir -p ~/.stash
cat > ~/.stash/config.json << 'STASH_CONFIG'
{config}
STASH_CONFIG
chmod 600 ~/.stash/config.json
claude plugin marketplace add Fergana-Labs/stash
claude plugin install stash@stash-plugins
mkdir -p {SPRITE_WORKDIR}
cat > {SPRITE_WORKDIR}/CLAUDE.md << 'WORKSPACE_CLAUDE_MD'
{claude_md}
WORKSPACE_CLAUDE_MD
stash skills sync
"""


async def _register_skills_sync_service(sprite: Sprite) -> None:
    """Keep Stash skills materialized on the box via a runtime-managed Service
    (restarts on cold wake). Endpoint shape verified in the staging pass."""
    await _sprites_api(
        "POST",
        f"/v1/sprites/{sprite.name}/services",
        json={
            "name": "stash-skills-sync",
            "cmd": f"bash -c 'export PATH=\"{SPRITE_PATH}\"; "
            "while true; do stash skills sync || true; sleep 300; done'",
        },
    )


async def touch(user_id: UUID) -> None:
    """Record agent activity (analytics; sleep is managed by Sprites itself)."""
    await get_pool().execute(
        "UPDATE user_sprites SET last_active_at = now() WHERE user_id = $1", user_id
    )


# ---------------------------------------------------------------------------
# Exec
# ---------------------------------------------------------------------------


async def exec_stream(
    sprite: Sprite,
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: str | None = None,
) -> AsyncIterator[dict]:
    """Run argv on the box, yielding {"stream": "stdout"|"stderr", "data": bytes}
    chunks and finally {"exit_code": int}. stdin is closed."""
    if settings.AGENT_EXEC_MODE == "local":
        async for event in _local_exec_stream(argv, env=env, cwd=cwd):
            yield event
        return
    async for event in _sprites_exec_stream(sprite, argv, env=env, cwd=cwd):
        yield event


async def exec_collect(
    sprite: Sprite,
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: str | None = None,
    timeout_s: int,
) -> tuple[str, int]:
    """Run argv to completion; returns (combined output, exit code)."""

    async def _drain() -> tuple[str, int]:
        chunks: list[bytes] = []
        exit_code = -1
        async for event in exec_stream(sprite, argv, env=env, cwd=cwd):
            if "data" in event:
                chunks.append(event["data"])
            else:
                exit_code = event["exit_code"]
        return b"".join(chunks).decode("utf-8", "replace"), exit_code

    return await asyncio.wait_for(_drain(), timeout=timeout_s)


def _sprite_env(extra: dict[str, str]) -> dict[str, str]:
    # The Sprites `env` param replaces the default environment entirely, so
    # every exec carries the full set the command needs.
    return {"HOME": SPRITE_HOME, "PATH": SPRITE_PATH, "TERM": "xterm-256color", **extra}


async def _sprites_exec_stream(
    sprite: Sprite,
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: str | None,
) -> AsyncIterator[dict]:
    params: list[tuple[str, str]] = [("cmd", part) for part in argv]
    params += [("env", f"{k}={v}") for k, v in _sprite_env(env).items()]
    if cwd:
        params.append(("dir", cwd))

    ws_base = settings.SPRITES_API_URL.replace("https://", "wss://", 1)
    url = f"{ws_base}/v1/sprites/{sprite.name}/exec?{urlencode(params)}"
    headers = {"Authorization": f"Bearer {settings.SPRITES_TOKEN}"}

    async with websockets.connect(url, additional_headers=headers, max_size=None) as ws:
        async for frame in ws:
            if not isinstance(frame, bytes):
                continue  # JSON control messages (resize, session info)
            if not frame:
                continue
            tag, payload = frame[0], frame[1:]
            if tag == _FRAME_STDOUT:
                yield {"stream": "stdout", "data": payload}
            elif tag == _FRAME_STDERR:
                yield {"stream": "stderr", "data": payload}
            elif tag == _FRAME_EXIT:
                yield {"exit_code": int(payload.decode())}
                return
    raise SpriteError("sprite exec stream closed without an exit frame")


def _local_workdir() -> Path:
    return Path.home() / ".stash-dev-sprite" / "work"


async def _local_exec_stream(
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: str | None,
) -> AsyncIterator[dict]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **env},
        cwd=cwd or str(_local_workdir()),
    )
    assert proc.stdout is not None and proc.stderr is not None

    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def _pump(reader: asyncio.StreamReader, stream: str) -> None:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            await queue.put({"stream": stream, "data": chunk})

    pumps = asyncio.gather(_pump(proc.stdout, "stdout"), _pump(proc.stderr, "stderr"))
    pumps.add_done_callback(lambda _: queue.put_nowait(None))
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
        yield {"exit_code": await proc.wait()}
    finally:
        if proc.returncode is None:
            proc.kill()
        with contextlib.suppress(asyncio.CancelledError):
            await pumps


# ---------------------------------------------------------------------------
# Keep-awake (Sprites pause severs TCP; a paused box would kill a mid-turn
# exec stream. A Task holds the sprite up; we refresh it for long turns.)
# ---------------------------------------------------------------------------

_TASK_TTL_S = 300
_TASK_REFRESH_S = 60


@contextlib.asynccontextmanager
async def hold_awake(sprite: Sprite) -> AsyncIterator[None]:
    if settings.AGENT_EXEC_MODE == "local":
        yield
        return

    async def _refresh_forever() -> None:
        while True:
            await _sprites_api(
                "POST",
                f"/v1/sprites/{sprite.name}/tasks",
                json={"name": "agent-turn", "ttl": _TASK_TTL_S},
            )
            await asyncio.sleep(_TASK_REFRESH_S)

    refresher = asyncio.create_task(_refresh_forever())
    try:
        yield
    finally:
        refresher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await refresher


# ---------------------------------------------------------------------------
# Sprites REST client
# ---------------------------------------------------------------------------


async def _sprites_api(method: str, path: str, *, json: dict | None = None) -> dict:
    async with httpx.AsyncClient(
        base_url=settings.SPRITES_API_URL,
        headers={"Authorization": f"Bearer {settings.SPRITES_TOKEN}"},
        timeout=30,
    ) as client:
        resp = await client.request(method, path, json=json)
        if resp.status_code >= 400:
            raise SpriteError(f"sprites API {method} {path} -> {resp.status_code}: {resp.text}")
        if not resp.content:
            return {}
        return resp.json()
