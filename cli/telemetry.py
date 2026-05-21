"""Fire-and-forget telemetry for stash CLI commands.

Posts a single analytics_events row per invocation. Network errors are
swallowed silently so telemetry never breaks a user command. Opt-out via
STASH_TELEMETRY=0.
"""

from __future__ import annotations

import os
import threading

import httpx

from .config import load_config


def _telemetry_enabled() -> bool:
    return os.environ.get("STASH_TELEMETRY", "1") != "0"


def _post(base_url: str, api_key: str, command: str) -> None:
    try:
        with httpx.Client(base_url=base_url, timeout=3) as c:
            c.post(
                "/api/v1/analytics/events",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "events": [
                        {
                            "surface": "cli",
                            "event_name": "cli.command_invoked",
                            "properties": {"command": command},
                        }
                    ]
                },
            )
    except Exception:
        # Telemetry is best-effort. If the backend is down, the user
        # invoking `stash share` shouldn't see a stack trace.
        pass


def record(command: str) -> None:
    if not _telemetry_enabled():
        return
    cfg = load_config()
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "")
    if not api_key or not base_url:
        return
    t = threading.Thread(target=_post, args=(base_url, api_key, command), daemon=True)
    t.start()
