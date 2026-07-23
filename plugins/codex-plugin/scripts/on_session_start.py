#!/usr/bin/env python3
"""Codex SessionStart: save session_id and create the session record."""

import json
import os
import shutil
import subprocess

from adapt import adapt_session_start
from config import DATA_DIR, get_client, get_config, get_stdin_data

from stashai.plugin.agent_config import cli_config
from stashai.plugin.hooks import (
    color_upload_health_warning,
    create_session_record,
    reset_session_record_state,
    uploads_disabled_warning,
    uploads_enabled,
)
from stashai.plugin.session_upload import spawn_session_watcher, spawn_skills_sync
from stashai.plugin.state import load_state, reset_stats, save_state

_ASK_AUTO_UPDATE = (
    "Stash: Codex auto-update isn't configured yet. Ask the user whether Stash "
    "should update itself automatically at session start. Pros: the hook runtime "
    "stays current with the Stash backend. Cons: the stash CLI can change under "
    "you mid-project. Record the answer by running `stash hook auto-update on` "
    "or `stash hook auto-update off`."
)


def _auto_update_message() -> str | None:
    """Returns the ask-the-user prompt until a preference is recorded; when
    auto-update is on, kicks off the background upgrade instead."""
    pref = cli_config().get("codex_auto_update")
    if pref is None:
        return _ASK_AUTO_UPDATE
    if pref and shutil.which("uv"):
        subprocess.Popen(
            ["uv", "tool", "install", "--quiet", "stashai@latest"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    return None


def main():
    event = adapt_session_start(get_stdin_data())
    cfg = get_config()
    state = load_state(DATA_DIR)
    if not uploads_enabled(cfg):
        warning = uploads_disabled_warning(cfg, state, event, DATA_DIR)
        if warning:
            print(json.dumps({"systemMessage": color_upload_health_warning(warning)}))
        return

    reset_session_record_state(state)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)
    state = load_state(DATA_DIR)

    try:
        with get_client() as client:
            create_session_record(client, cfg, state, event, DATA_DIR)
    except Exception:
        return

    spawn_skills_sync(cfg)

    if state.get("session_row_id"):
        spawn_session_watcher(
            agent_pid=os.getppid(),
            session_id=event.session_id,
            agent_name=cfg.get("agent_name", ""),
            base_url=cfg.get("api_endpoint", ""),
            api_key=cfg.get("api_key", ""),
            cwd=event.cwd or "",
            data_dir=DATA_DIR,
            session_row_id=state.get("session_row_id", ""),
            transcript_path=event.transcript_path,
        )

    message = _auto_update_message()
    if message:
        print(json.dumps({"systemMessage": message}))


if __name__ == "__main__":
    main()
