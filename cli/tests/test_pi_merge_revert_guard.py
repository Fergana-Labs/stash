"""Anti-merge-revert guard for the Pi CLI installer wiring.

STAS-072 silently reverted the pi CLI wiring on main: ``"pi"`` was dropped from
``_SUPPORTED_AGENTS`` / ``_AGENT_BINARY`` / ``_INSTALLERS`` and
``cli/tests/test_install_pi.py`` was deleted, and nothing failed loudly, so the
regression shipped unnoticed. STAS-085 restored the wiring on the local main
line; these tests make the revert shape impossible to land silently again.

STAS-083's pi entries in the no-swallow sweep (``plugins/tests``) and
``test_assets_in_sync.py`` byte-parity stop pi *code* regressions; this module
guards the specific merge-revert shape on the CLI wiring: the list membership
``"pi" in _SUPPORTED_AGENTS`` is the intentional sentinel that catches pi being
dropped from the tuple, the binary map, and the installers all at once.
The data-dir sentinel ``"pi" in PLUGIN_DATA_DIRS`` catches the STAS-100
partial-port shape that the ``_SUPPORTED_AGENTS`` sentinel misses: the port
kept the other 7 pi wiring rows but dropped the data-dir entry, so
status/settings/upload-health listings silently omitted pi.
"""

from __future__ import annotations

from pathlib import Path

from cli.main import _SUPPORTED_AGENTS, PLUGIN_DATA_DIRS

# The guard lives next to test_install_pi.py in cli/tests; parents[1] is the
# cli/ package dir, so cli/tests/test_install_pi.py is parents[1]/tests/....
PI_INSTALLER_TEST = Path(__file__).resolve().parents[1] / "tests" / "test_install_pi.py"


def test_pi_present_in_supported_agents():
    """A merge that drops pi from _SUPPORTED_AGENTS must fail loudly.

    STAS-072's revert dropped "pi" from _SUPPORTED_AGENTS, _AGENT_BINARY, and
    _INSTALLERS together, so this single membership assertion is the sentinel
    for the whole wiring, not just the tuple.
    """
    assert "pi" in _SUPPORTED_AGENTS, (
        '"pi" was dropped from cli.main._SUPPORTED_AGENTS '
        f"(got {_SUPPORTED_AGENTS!r}). A merge reverted the STAS-072-style pi "
        "CLI wiring; restore it from STAS-085 (023094b5) rather than silencing "
        "this check."
    )


def test_pi_present_in_plugin_data_dirs():
    """A port that drops pi from PLUGIN_DATA_DIRS must fail loudly.

    STAS-100's port kept the other 7 pi wiring rows but dropped the data-dir
    entry, so status/settings/upload-health listings silently omitted pi even
    while the plugin recorded. Membership only: the guard is not coupled to
    the concrete dir scheme.
    """
    assert "pi" in PLUGIN_DATA_DIRS, (
        '"pi" was dropped from cli.main.PLUGIN_DATA_DIRS '
        f"(got {sorted(PLUGIN_DATA_DIRS)!r}). STAS-100's partial port kept the "
        "other 7 pi wiring rows but dropped the data-dir entry; restore the "
        "row from STAS-085 (023094b5) rather than silencing this check."
    )


def test_pi_installer_test_present():
    """STAS-072 also deleted test_install_pi.py; its loss must fail loudly.

    Guards against both the file being removed and it being reduced to an
    empty/stub shadow that no longer exercises the installer.
    """
    assert PI_INSTALLER_TEST.is_file(), (
        f"{PI_INSTALLER_TEST.relative_to(Path(__file__).resolve().parents[2])} "
        "is missing. STAS-072 removed cli/tests/test_install_pi.py in a stray "
        "merge; restore it so the installer stays covered."
    )
    assert PI_INSTALLER_TEST.stat().st_size > 0, (
        f"{PI_INSTALLER_TEST.relative_to(Path(__file__).resolve().parents[2])} "
        "is empty. Restore the real pi installer regression tests (see STAS-085 "
        "source) instead of leaving a stub."
    )
