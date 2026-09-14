"""The servers we bundle, by the name a skill declares them under.

Each entry builds a FastMCP whose tools already read the calling user via
`current_user()`. Trained models contribute one server per kind; a future
skill with its own tools (a research helper, a deck builder) adds a line.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from mcp.server.fastmcp import FastMCP

from ..trained_models import mcp as trained_models_mcp
from ..trained_models import registry as trained_models_registry

SERVERS: dict[str, Callable[[], FastMCP]] = {
    kind: partial(trained_models_mcp.build, kind) for kind in trained_models_registry.KINDS
}
