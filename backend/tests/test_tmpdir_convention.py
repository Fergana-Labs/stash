"""STAS-118: verification temp files must land on the /home volume, never /tmp.

/tmp is a shared 63G tmpfs that intermittently fills — on 2026-08-23 ENOSPC
crashed pytest temp-file creation during STAS-105 verification. conftest.py
defaults TMPDIR to $HOME/.tmp when the operator hasn't set one; this file is
the regression guard for that contract.
"""

import os
import tempfile


def test_pytest_tmp_path_lands_on_home_volume(tmp_path):
    home_tmp = os.path.join(os.environ["HOME"], ".tmp")
    assert str(tmp_path).startswith(home_tmp)
    assert not str(tmp_path).startswith("/tmp/")


def test_tempfile_gettempdir_follows_convention():
    home_tmp = os.path.join(os.environ["HOME"], ".tmp")
    assert tempfile.gettempdir().startswith(home_tmp)
