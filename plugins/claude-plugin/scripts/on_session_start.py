#!/usr/bin/env python3
"""SessionStart: save session_id for downstream streaming, and inject a
context message so the agent knows the stash CLI is on its PATH."""

import json
import sys
from urllib.parse import urlparse

from config import DATA_DIR, _load_cli_config, get_config, get_stdin_data, is_configured
from stashai.plugin.state import load_state, reset_stats, save_state

from adapt import adapt_session_start


def _frontend_url(api_url: str) -> str:
    """Derive the web dashboard URL from the API base URL.

    api.joinstash.ai → app.joinstash.ai, etc.
    """
    parsed = urlparse(api_url)
    host = parsed.hostname or ""
    if host.startswith("api."):
        host = f"app.{host[4:]}"
    if "localhost" in host or "127.0.0.1" in host:
        port = parsed.port + 1 if parsed.port else 3457
        return f"{parsed.scheme}://{host}:{port}"
    return f"{parsed.scheme}://{host}"


def _build_context() -> str:
    cfg = get_config()
    api_url = cfg.get("api_endpoint", "")
    workspace_id = cfg.get("workspace_id", "") or _load_cli_config().get("default_workspace", "")

    parts = [
        "You have the `stash` CLI on your PATH. Run `stash --help` to see commands. "
        "Use it to read transcripts, notebooks, and history from your team's shared "
        "Stash workspace. Your activity in this repo is streamed to that workspace, "
        "so teammates' agents and humans can see what you're working on.",
    ]

    if api_url:
        web_url = _frontend_url(api_url)
        if workspace_id:
            parts.append(
                f"The web dashboard for this workspace is at {web_url}/workspaces/{workspace_id} ."
            )
        else:
            parts.append(f"The Stash web dashboard is at {web_url} .")

    parts.append(
        "Common reads (all support `--json`): "
        "`stash history search \"<query>\"`, "
        "`stash history query --limit 20`, "
        "`stash history agents`, "
        "`stash notebooks list --all`."
    )

    return " ".join(parts)


def main():
    if not is_configured():
        return

    event = adapt_session_start(get_stdin_data())

    state = load_state(DATA_DIR)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": _build_context(),
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
