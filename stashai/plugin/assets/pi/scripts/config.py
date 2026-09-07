"""Pi agent plugin config. Reads from ~/.stash/config.json (CLI config).

Shared logic lives in `stashai.plugin.agent_config`; this module only
supplies the per-agent constants.
"""

from __future__ import annotations

import os

from stashai.plugin import agent_config
from stashai.plugin.agent_config import get_stdin_data
from stashai.plugin.stash_client import StashClient

_CLIENT = "pi"
DATA_DIR = agent_config.data_dir_from_env("STASH_PI_DATA", ".stash/plugins/pi")

__all__ = [
    "DATA_DIR",
    "get_client",
    "get_config",
    "get_stdin_data",
    "is_configured",
    "is_fusion_managed",
]


def get_config() -> dict:
    return agent_config.get_config(_CLIENT)


def get_client() -> StashClient:
    return agent_config.get_client(_CLIENT, DATA_DIR)


def is_configured() -> bool:
    return agent_config.is_configured(_CLIENT)


def is_fusion_managed(cwd: str | None) -> bool:
    """True when a session runs inside a Fusion project directory.

    Variant-1 guard: pi-plugin must stay silent for sessions whose working
    directory is inside a Fusion project (a directory containing `.fusion/`).
    There, Fusion's own engine session capture is the canonical recorder, so
    recording from pi-hooks as well would double-record the same conversation
    into Stash (once as `sess_*`, once as `fusion-<taskId>-<hash>`). Sessions
    outside Fusion projects (standalone `pi` usage) are still recorded.

    An empty/None cwd fails loud with ValueError rather than silently choosing
    the "record" direction the guard exists to prevent.
    """
    if not cwd:
        raise ValueError(
            "is_fusion_managed requires a non-empty cwd; refusing to guess the recording direction"
        )
    home = os.path.expanduser("~")
    d = os.path.abspath(cwd)
    while True:
        # Marker must never match the global Fusion config dir at $HOME/.fusion
        # (daemon token / global settings). Walking the whole tree up to /
        # would classify every Pi session under $HOME as Fusion-managed and
        # silently stop all recording on the machine.
        if d != home and os.path.isdir(os.path.join(d, ".fusion")):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent
