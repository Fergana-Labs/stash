#!/usr/bin/env python3
"""SessionStart: save session_id, create the session row, upload artifacts later,
and inject context."""

import json
import os
import sys

from adapt import adapt_session_start
from config import DATA_DIR, get_config, get_stdin_data

try:
    from stashai.plugin.doctor import shadow_install_warning
except ImportError:
    # Plugin scripts can refresh a session before the stashai package
    # auto-updates; skip the check until the package catches up.
    def shadow_install_warning() -> None:
        return None


from stashai.plugin.hooks import (
    create_session_record,
    reset_session_record_state,
    uploads_disabled_warning,
    uploads_enabled,
)
from stashai.plugin.session_upload import spawn_session_watcher, spawn_skills_sync
from stashai.plugin.state import load_state, reset_stats, save_state

CONTEXT = (
    "You have the `stash` CLI on your PATH. Run `stash --help` to see commands. "
    "Your activity in this repo is streamed to your team's Stash workspace.\n\n"
    "What a Skill is: a *special folder* (one containing a SKILL.md) of related "
    "files, tables) that shares like any folder and gains a public URL when "
    "published. A Skill is for a collection — a project writeup with its "
    "supporting files, a research thread with its sources. It is NOT a "
    "wrapper to slap on every single file you share.\n\n"
    "When sharing artifacts, pick the right tool:\n"
    " - Single file your teammate should look at → `stash files upload "
    "<path> --json` and hand them the returned `app_url`. NO Skill needed.\n"
    " - Upload a folder/project into the workspace → `stash upload <path> "
    "--json` returns the folder `app_url`. NO Skill created by default.\n"
    " - You're publishing a curated bundle people should see together → "
    '`stash upload <path> --skill "<title>" --json` (or `stash skills '
    "create` to compose from existing items).\n"
    " - Sharing a coding session → `stash share <session_id>` wraps the "
    "transcript and touched files in one Skill. Don't ALSO mint a Skill "
    "for each file in that session.\n"
    " - Using a public Skill locally → `stash skills install <slug>` "
    "writes it into ~/.claude/skills so it loads next session "
    "(`--project` for ./.claude/skills).\n\n"
    "Run `stash prompts agent-guidance` any time you want this guidance "
    "reprinted in full.\n\n"
    "Browse Stash through the virtual filesystem first when you need workspace "
    'context: `stash vfs ls /`, `stash vfs "find /workspaces -maxdepth 3 '
    '-type f"`, `stash vfs "rg \\"query\\" /workspaces"`, or '
    "`stash vfs \"cat '/workspaces/<workspace>/README.md' | sed -n "
    "'1,80p'\"`.\n\n"
    "Common direct reads (all support `--json`): "
    '`stash sessions search "<query>"`, '
    "`stash sessions query --limit 20`, "
    "`stash sessions agents`, "
    "`stash files pages --all`."
)

SESSION_CONTEXT = (
    "\nSession record: {url}\n"
    "IMPORTANT: Always include this session record link at the end of every "
    "response you give, formatted as: Session: {url}"
)


def main():
    event = adapt_session_start(get_stdin_data())
    cfg = get_config()

    state = load_state(DATA_DIR)
    if not uploads_enabled(cfg, event):
        warning = uploads_disabled_warning(cfg, state, event, DATA_DIR)
        messages = [m for m in (warning, shadow_install_warning()) if m]
        if messages:
            json.dump({"systemMessage": "\n\n".join(messages)}, sys.stdout)
        return

    reset_session_record_state(state)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)
    state = load_state(DATA_DIR)

    session_context = ""
    try:
        from config import get_client

        with get_client() as client:
            session_url = create_session_record(client, cfg, state, event, DATA_DIR)
    except Exception:
        session_url = None

    spawn_skills_sync(
        cfg, state.get("uploaded_workspace_id") or cfg.get("workspace_id", "")
    )

    if session_url:
        session_context = "\n" + SESSION_CONTEXT.format(url=session_url)
        spawn_session_watcher(
            agent_pid=os.getppid(),
            session_id=event.session_id,
            workspace_id=state.get("uploaded_workspace_id") or cfg.get("workspace_id", ""),
            agent_name=cfg.get("agent_name", ""),
            base_url=cfg.get("api_endpoint", ""),
            api_key=cfg.get("api_key", ""),
            cwd=event.cwd or "",
            data_dir=DATA_DIR,
            session_row_id=state.get("session_row_id", ""),
        )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": CONTEXT + session_context,
        }
    }
    shadow_warning = shadow_install_warning()
    if shadow_warning:
        output["systemMessage"] = shadow_warning
    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
