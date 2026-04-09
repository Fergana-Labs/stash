"""Smoke test: Alembic can run upgrade head on a clean database."""

import os
import subprocess
import sys

import pytest


def test_alembic_upgrade_head():
    """alembic upgrade head completes without error on the test database."""
    db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://octopus:octopus@localhost:5432/octopus_test",
    )
    # Temporarily set DATABASE_URL for the subprocess
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_alembic_history_is_linear():
    """alembic history must not contain branches or merge points."""
    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "history", "--verbose"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # No branch or merge markers in a linear chain
    assert "Branch" not in result.stdout
    assert "Merge" not in result.stdout
