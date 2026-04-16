"""Default the scope gate to wide-open for pre-existing tests that don't
set up install_repo_common_dir. Per-test scope tests re-patch this."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _scope_wide_open(monkeypatch):
    # Only patch the binding that hooks.py uses. Tests that import
    # scope.cwd_in_scope directly (scope.py's own tests) get the real thing.
    from stashai.plugin import hooks
    monkeypatch.setattr(hooks, "cwd_in_scope", lambda cwd, cfg: True)
