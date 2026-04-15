"""Codex CLI plugin config. Reads from ~/.octopus/config.json (CLI config)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parent.parent.parent / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from octopus_client import OctopusClient  # noqa: E402

DATA_DIR = Path(os.environ.get(
    "OCTOPUS_CODEX_DATA",
    Path.home() / ".octopus/plugins/codex",
))

ESCALATION_DIR = Path(os.environ.get(
    "OCTOPUS_NOTIFICATIONS_DIR",
    Path.home() / ".octopus/notifications",
))


def get_stdin_data() -> dict:
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _project_config() -> Path | None:
    try:
        cur = Path.cwd().resolve()
    except Exception:
        return None
    for parent in [cur, *cur.parents]:
        candidate = parent / ".octopus" / "config.json"
        if candidate.exists():
            return candidate
    return None


def _cli_config() -> dict:
    merged: dict = {}
    user_path = Path.home() / ".octopus" / "config.json"
    if user_path.exists():
        merged.update(_read_json(user_path))
    project_path = _project_config()
    if project_path:
        merged.update(_read_json(project_path))
    return merged


def get_config() -> dict:
    cli = _cli_config()
    return {
        "api_endpoint": cli.get("base_url", "https://getoctopus.com"),
        "api_key": cli.get("api_key", ""),
        "agent_name": cli.get("username", ""),
        "workspace_id": cli.get("default_workspace", ""),
        "inject_context": os.environ.get("OCTOPUS_INJECT_CONTEXT", "true"),
        "auto_curate": os.environ.get("OCTOPUS_AUTO_CURATE", "false"),
        "client": "codex_cli",
    }


def get_client() -> OctopusClient:
    cfg = get_config()
    return OctopusClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"])


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["api_key"] and cfg["agent_name"])
