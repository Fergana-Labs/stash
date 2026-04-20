"""Plugin asset templates shipped with stashai.

Each agent directory mirrors `plugins/<agent>-plugin/` in the source repo.
`stash connect` reads these to install hook configs into `~/.<agent>/` without
requiring the user to clone the stash repo.

The source-of-truth is `plugins/<agent>-plugin/`; a drift test in
`plugins/tests/test_assets_in_sync.py` keeps the two identical.
"""

from pathlib import Path


def assets_dir(agent: str) -> Path:
    """Absolute path to the shipped plugin assets for a given agent."""
    here = Path(__file__).parent
    path = here / agent
    if not path.is_dir():
        raise FileNotFoundError(f"No shipped plugin assets for agent '{agent}' at {path}")
    return path
