"""Spawn detached background processes for session artifact upload."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from stashai.plugin.upload_status import record_upload_failure

# Global skills directory each agent loads SKILL.md folders from at session
# start. Codex, Gemini, and OpenCode all read the cross-agent ~/.agents/skills
# standard, so they converge on one synced copy. Claude Code reads its own
# ~/.claude/skills (it does not scan .agents); OpenClaw uses ~/.openclaw/skills.
# Cursor is omitted: it only loads project-level .cursor/skills with no global
# location, so there's nothing to sync at session start.
# Hermes loads ~/.hermes/skills natively; ~/.agents/skills only counts if the
# user opts into skills.external_dirs, so we sync to the always-loaded dir.
_SKILLS_DIR_BY_CLIENT = {
    "claude_code": "~/.claude/skills",
    "codex_cli": "~/.agents/skills",
    "gemini_cli": "~/.agents/skills",
    "opencode": "~/.agents/skills",
    "openclaw": "~/.openclaw/skills",
    "hermes": "~/.hermes/skills",
}


def spawn_skills_sync(cfg: dict) -> None:
    """Sync the user's skills into the agent's skills directory in the
    background, so they're loaded next session. Detached and silent — a failed
    sync must never break a session. No-op for agents without a global skills
    directory (e.g. Cursor, which is project-only)."""
    skills_dir = _SKILLS_DIR_BY_CLIENT.get(cfg.get("client", ""))
    if not skills_dir:
        return
    cmd = ["stash", "skills", "sync", "--dir", skills_dir]
    env = dict(os.environ)
    if cfg.get("api_endpoint"):
        env["STASH_URL"] = cfg["api_endpoint"]
    if cfg.get("api_key"):
        env["STASH_API_KEY"] = cfg["api_key"]
    try:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            env=env,
        )
    except Exception:
        pass


def spawn_self_upgrade() -> None:
    """Background-upgrade the stashai install at session start. The hook
    scripts ship inside the package (`stash hook run` executes them), so
    upgrading the package keeps library and scripts current in lockstep.
    Detached and silent — an upgrade must never block or break a session."""
    if not shutil.which("uv"):
        return
    subprocess.Popen(
        ["uv", "tool", "install", "--quiet", "stashai@latest"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def spawn_session_watcher(
    agent_pid: int,
    session_id: str,
    agent_name: str,
    base_url: str,
    api_key: str,
    cwd: str,
    data_dir: Path,
    session_row_id: str,
    transcript_path: str = "",
) -> bool:
    """Watch an agent process and finalize session artifacts after it exits."""
    script = Path(__file__).parent / "_session_watcher.py"
    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                str(agent_pid), session_id, agent_name,
                base_url, api_key, cwd, str(data_dir), session_row_id, transcript_path,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        return False
    return True


def spawn_session_upload(
    session_row_id: str,
    transcript_path: str,
    cwd: str,
    files_touched: list[str],
    session_id: str,
    agent_name: str,
    base_url: str,
    api_key: str,
    data_dir: Path | None = None,
) -> bool:
    script = Path(__file__).parent / "_do_session_upload.py"
    env = os.environ.copy()
    env["SESSION_FILES_TOUCHED"] = json.dumps(files_touched)
    upload_status_dir = str(data_dir or "")

    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                session_row_id, transcript_path, cwd, session_id,
                agent_name, base_url, api_key, upload_status_dir,
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception as e:
        record_upload_failure(data_dir, "artifact_spawn", e)
        return False
    return True
