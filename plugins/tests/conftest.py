"""Default the streaming gate to wide-open for tests that don't configure it.
Per-test scope tests re-patch this."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _scope_wide_open(monkeypatch):
    # Force the global streaming gate on for hooks-driven tests. scope.py's own
    # tests exercise the real gate directly.
    from stashai.plugin import hooks

    monkeypatch.setattr(hooks, "streaming_enabled", lambda *a, **k: True)
