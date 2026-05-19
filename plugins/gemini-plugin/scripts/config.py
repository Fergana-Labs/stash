"""Gemini CLI plugin config. Reads from ~/.stash/config.json (CLI config).

Shared logic lives in `stashai.plugin.agent_config`; this module only
supplies the per-agent constants.
"""

from __future__ import annotations

from stashai.plugin import agent_config
from stashai.plugin.agent_config import get_stdin_data
from stashai.plugin.stash_client import StashClient

_CLIENT = "gemini_cli"
DATA_DIR = agent_config.data_dir_from_env("STASH_GEMINI_DATA", ".stash/plugins/gemini")

__all__ = ["DATA_DIR", "get_client", "get_config", "get_stdin_data", "is_configured"]


def get_config() -> dict:
    return agent_config.get_config(_CLIENT)


def get_client() -> StashClient:
    return agent_config.get_client(_CLIENT, DATA_DIR)


def is_configured() -> bool:
    return agent_config.is_configured(_CLIENT)
