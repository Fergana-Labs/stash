"""
Create a fresh stash workspace and push seed events into it via the `stash` CLI.

This uses the stash CLI binary rather than the REST API so we exercise the same
code path a human would. The CLI reads auth from STASH_CONFIG_DIR (or
~/.stash/config.json).

Returns the workspace_id so the runner can wire the plugin to it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def run(cmd: list[str], env: dict[str, str] | None = None) -> str:
    """Run a command and return stdout. Raise on non-zero exit."""
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout


def create_workspace(name: str, env: dict[str, str]) -> str:
    """Create a new workspace and return its id."""
    out = run(["stash", "workspaces", "create", name, "--json"], env=env)
    data = json.loads(out)
    return data["id"]


def push_events(workspace_id: str, events: list[dict], env: dict[str, str]) -> None:
    """Push each event to the workspace."""
    for ev in events:
        cmd = [
            "stash",
            "history",
            "push",
            ev["text"],
            "--ws",
            workspace_id,
            "--agent",
            "claude-session-a",
            "--type",
            ev.get("type", "note"),
        ]
        run(cmd, env=env)


def seed(name: str, events_path: str, env: dict[str, str]) -> str:
    """Create a workspace, push events, return workspace_id."""
    workspace_id = create_workspace(name, env)
    with open(events_path) as f:
        events = json.load(f)
    push_events(workspace_id, events, env)
    return workspace_id


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: seed_workspace.py <workspace_name> <seed_events.json>", file=sys.stderr)
        sys.exit(2)
    name = sys.argv[1]
    events_path = sys.argv[2]
    env = os.environ.copy()
    workspace_id = seed(name, events_path, env)
    print(workspace_id)


if __name__ == "__main__":
    main()
