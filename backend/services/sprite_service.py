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

# Sprites run as the (sudo-capable) `sprite` user. The harness CLIs live in
# ~/.local/bin and the runtime's python/node in /.sprite/bin; env params REPLACE
# the environment, so execs must carry the full PATH the box normally has.
SPRITE_HOME = "/home/sprite"
SPRITE_WORKDIR = f"{SPRITE_HOME}/work"
SPRITE_PATH = (
    f"{SPRITE_HOME}/.local/bin:/.sprite/bin:"
    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
)

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
    plugin (session upload), skills, and the workspace.

    Skills are synced here (not via a polling service) on purpose: a periodic
    daemon would count as activity and keep the box awake 24/7, defeating the
    sleep-to-zero cost model. Live skill re-sync is a fast-follow (sync at
    turn start), not a background loop."""
    config = json.dumps(
        {"base_url": settings.SPRITES_STASH_API_URL, "api_key": stash_key, "username": ""}
    )
    claude_md = prompts.render_sprite_workspace_claude_md()
    return f"""
set -euo pipefail
export PATH="{SPRITE_PATH}"
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
    stdout_only: bool = False,
) -> tuple[str, int]:
    """Run argv to completion; returns (output, exit code).

    stdout_only excludes stderr — required for callers that strictly parse the
    output (JSON/base64), since Sprites merges stderr into the stream and a
    stray warning would corrupt the parse.
    """

    async def _drain() -> tuple[str, int]:
        chunks: list[bytes] = []
        exit_code = -1
        async for event in exec_stream(sprite, argv, env=env, cwd=cwd):
            if "exit_code" in event:
                exit_code = event["exit_code"]
            elif not stdout_only or event["stream"] == "stdout":
                chunks.append(event["data"])
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
                # The exit code is a single raw byte, not an ASCII string.
                yield {"exit_code": payload[0] if payload else 0}
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
    # Callers name box paths; the simulated box's workdir lives under $HOME.
    local_cwd = _local_workdir() if cwd in (None, SPRITE_WORKDIR) else Path(cwd)
    local_cwd.mkdir(parents=True, exist_ok=True)
    # Local mode means "this machine's own claude login" — the backend's
    # ANTHROPIC_API_KEY (loaded into os.environ by dotenv) must not leak into
    # the child, or it overrides that login. Explicit `env` still wins.
    inherited = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**inherited, **env},
        cwd=str(local_cwd),
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
# Filesystem read-through (the "Computer" projection in the VFS/sidebar)
# ---------------------------------------------------------------------------

# Listing and reading ride the exec seam (a python3 one-liner on the box), so
# they work identically in both exec modes with no extra API surface.

FS_MAX_READ_BYTES = 2 * 1024 * 1024

_FS_LIST_PY = (
    "import json,os,sys\n"
    "p=sys.argv[1]\n"
    "out=[]\n"
    "for e in sorted(os.scandir(p), key=lambda e:(not e.is_dir(),e.name.lower())):\n"
    "    st=e.stat(follow_symlinks=False)\n"
    "    out.append({'name':e.name,'dir':e.is_dir(),'size':st.st_size,'mtime':int(st.st_mtime)})\n"
    "print(json.dumps(out))\n"
)


class FsPathError(ValueError):
    """A path escaped the box home or doesn't resolve."""


def _box_path(rel_path: str) -> str:
    """Resolve a home-relative path to an absolute box path, refusing escapes."""
    import posixpath

    home = SPRITE_HOME if settings.AGENT_EXEC_MODE == "sprites" else str(_local_workdir().parent)
    joined = posixpath.normpath(posixpath.join(home, rel_path.lstrip("/")))
    if joined != home and not joined.startswith(home + "/"):
        raise FsPathError(f"path escapes the machine home: {rel_path}")
    return joined


async def write_file(sprite: Sprite, abs_path: str, contents: str) -> None:
    """Write a file on the box (absolute path). Used to materialize OAuth
    credential files before a turn. base64 avoids any quoting of the payload."""
    import base64

    b64 = base64.b64encode(contents.encode()).decode()
    script = (
        'import base64,os,sys;p=sys.argv[1];os.makedirs(os.path.dirname(p),exist_ok=True);'
        'open(p,"wb").write(base64.b64decode(sys.argv[2]));os.chmod(p,0o600)'
    )
    _, code = await exec_collect(
        sprite, ["python3", "-c", script, abs_path, b64], env={}, timeout_s=30
    )
    if code != 0:
        raise SpriteError(f"write_file failed for {abs_path}")


async def fs_list(sprite: Sprite, rel_path: str) -> list[dict]:
    """Directory entries at a home-relative path on the box."""
    output, code = await exec_collect(
        sprite,
        ["python3", "-c", _FS_LIST_PY, _box_path(rel_path)],
        env={},
        timeout_s=30,
        stdout_only=True,
    )
    if code != 0:
        raise SpriteError(f"fs list failed: {output[-500:]}")
    return json.loads(output)


async def fs_read(sprite: Sprite, rel_path: str) -> bytes:
    """A file's bytes from the box (capped at FS_MAX_READ_BYTES)."""
    import base64

    box_path = _box_path(rel_path)
    output, code = await exec_collect(
        sprite,
        ["python3", "-c", "import base64,sys;print(base64.b64encode(open(sys.argv[1],'rb').read(int(sys.argv[2]))).decode())", box_path, str(FS_MAX_READ_BYTES)],
        env={},
        timeout_s=60,
        stdout_only=True,
    )
    if code != 0:
        raise SpriteError(f"fs read failed: {output[-500:]}")
    return base64.b64decode(output.strip())


# ---------------------------------------------------------------------------
# Interactive terminal (PTY)
# ---------------------------------------------------------------------------


class Terminal:
    """An interactive shell on the user's box, bridged to a browser terminal.

    `output()` yields raw bytes; `send_input`/`resize` feed keystrokes and
    window-size changes in. Exactly two implementations, one per exec mode.
    """

    async def send_input(self, data: bytes) -> None:
        raise NotImplementedError

    async def resize(self, cols: int, rows: int) -> None:
        raise NotImplementedError

    def output(self) -> AsyncIterator[bytes]:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


async def open_terminal(sprite: Sprite, *, cols: int, rows: int) -> Terminal:
    if settings.AGENT_EXEC_MODE == "local":
        return await _LocalTerminal.open(cols=cols, rows=rows)
    return await _SpriteTerminal.open(sprite, cols=cols, rows=rows)


# Stdin frames to the Sprites tty exec are tagged like the output frames.
_FRAME_STDIN = 0x00


class _SpriteTerminal(Terminal):
    """WSS exec with tty=true against the user's sprite. The default sprite
    environment applies (no env params), so the shell looks like a login
    shell on the box — the Anthropic key is never in a terminal's env."""

    def __init__(self, ws) -> None:
        self._ws = ws

    @classmethod
    async def open(cls, sprite: Sprite, *, cols: int, rows: int) -> _SpriteTerminal:
        params: list[tuple[str, str]] = [
            ("cmd", "bash"),
            ("cmd", "-l"),
            ("tty", "true"),
            ("cols", str(cols)),
            ("rows", str(rows)),
            ("dir", SPRITE_WORKDIR),
        ]
        ws_base = settings.SPRITES_API_URL.replace("https://", "wss://", 1)
        url = f"{ws_base}/v1/sprites/{sprite.name}/exec?{urlencode(params)}"
        ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {settings.SPRITES_TOKEN}"},
            max_size=None,
        )
        return cls(ws)

    async def send_input(self, data: bytes) -> None:
        await self._ws.send(bytes([_FRAME_STDIN]) + data)

    async def resize(self, cols: int, rows: int) -> None:
        await self._ws.send(json.dumps({"type": "resize", "cols": cols, "rows": rows}))

    async def output(self) -> AsyncIterator[bytes]:
        async for frame in self._ws:
            if not isinstance(frame, bytes) or not frame:
                continue
            tag, payload = frame[0], frame[1:]
            if tag in (_FRAME_STDOUT, _FRAME_STDERR):
                yield payload
            elif tag == _FRAME_EXIT:
                return

    async def close(self) -> None:
        await self._ws.close()


class _LocalTerminal(Terminal):
    """A real PTY running the dev machine's shell (local exec mode)."""

    def __init__(self, proc, master_fd: int) -> None:
        self._proc = proc
        self._master_fd = master_fd

    @classmethod
    async def open(cls, *, cols: int, rows: int) -> _LocalTerminal:
        import pty

        master_fd, slave_fd = pty.openpty()
        _set_winsize(slave_fd, cols, rows)
        _local_workdir().mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            os.environ.get("SHELL", "bash"),
            "-l",
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(_local_workdir()),
            env={**os.environ, "TERM": "xterm-256color"},
            start_new_session=True,
        )
        os.close(slave_fd)
        return cls(proc, master_fd)

    async def send_input(self, data: bytes) -> None:
        os.write(self._master_fd, data)

    async def resize(self, cols: int, rows: int) -> None:
        _set_winsize(self._master_fd, cols, rows)

    async def output(self) -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, os.read, self._master_fd, 65536)
            except OSError:
                return  # PTY closed (shell exited)
            if not data:
                return
            yield data

    async def close(self) -> None:
        if self._proc.returncode is None:
            self._proc.kill()
        with contextlib.suppress(OSError):
            os.close(self._master_fd)


def _set_winsize(fd: int, cols: int, rows: int) -> None:
    import fcntl
    import struct
    import termios

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


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
