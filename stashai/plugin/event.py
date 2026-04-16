"""Canonical hook event shape, shared across all agent plugins.

Each per-agent plugin ships an adapt.py that turns its agent's raw stdin JSON
into a HookEvent. Everything downstream (streaming, summarizing, injection)
operates on HookEvent only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EventKind = Literal[
    "session_start",
    "prompt",
    "tool_use",
    "stop",
    "session_end",
]


@dataclass
class HookEvent:
    kind: EventKind
    session_id: str = ""
    cwd: str = ""

    # prompt
    prompt_text: str = ""

    # tool_use
    tool_name: str = ""           # normalized: "edit", "write", "bash", "read", "glob", "grep", "agent", ...
    tool_input: dict = field(default_factory=dict)
    tool_response: dict | None = None

    # stop / session_end
    last_assistant_message: str = ""
    transcript_path: str = ""     # optional — only agents that expose one

    # escape hatch for adapter-specific extras
    extras: dict = field(default_factory=dict)
