"""Hermetic execution of the real generated sprite seed script.

The exact bytes of ``_seed_script`` run under a stub PATH (fake
stash/opencode/claude/npm/pi executables plus symlinked coreutils), so the
npm/pi orderings are locked exactly as a box would see them:

- npm missing -> the seed fails with a precise, self-describing message
  (exit 1), not a bare "npm: command not found" (exit 127);
- npm present -> the pinned pi install with the exact npm arguments;
- pi present  -> idempotent no-op, npm never invoked.

The stub PATH is the *only* PATH (no /usr/bin:/bin tail): dev machines carry
/usr/bin/npm, which would make the missing-npm case untestable. Everything
the seed script needs as a real binary (bash, ln, mkdir, cat, chmod) is
symlinked into the stub dir.
"""

import os
import shutil
import subprocess
from pathlib import Path

from backend.services import sprite_service

# Real binaries the seed script uses (beyond the stubbed CLIs).
_COREUTILS = ("bash", "ln", "mkdir", "cat", "chmod")


class _SeedEnv:
    """One stub-armed execution environment for the generated seed script."""

    def __init__(self, tmp_path: Path, monkeypatch, *, with_npm: bool, with_pi: bool):
        self.stub = tmp_path / "stub-bin"
        self.stub.mkdir()
        for real in _COREUTILS:
            (self.stub / real).symlink_to(Path(shutil.which(real)).resolve())

        self.home = tmp_path / "home"
        self.home.mkdir()
        self.workdir = tmp_path / "work"
        self.prefix = tmp_path / "npm-prefix" / "lib"
        (self.prefix / "bin").mkdir(parents=True)

        self.calls_log = tmp_path / "calls.log"
        self.npm_log = tmp_path / "npm-calls.log"

        # Recorded no-ops: each stub is found on PATH, so its install branch
        # in the seed never runs, and every call lands in calls.log.
        for name in ("stash", "opencode", "claude"):
            self._write_stub(name, f'echo "{name} $*" >> "{self.calls_log}"')
        if with_npm:
            self._write_stub(
                "npm",
                f'echo "npm $*" >> "{self.npm_log}"\n'
                f'if [ "${{1:-}}" = "prefix" ]; then echo "{self.prefix}"; fi',
            )
        if with_pi:
            self._write_stub("pi", "exit 0")

        # Module constants the f-string reads at generation time.
        monkeypatch.setattr(sprite_service, "SPRITE_PATH", str(self.stub))
        monkeypatch.setattr(sprite_service, "SPRITE_WORKDIR", str(self.workdir))

    def _write_stub(self, name: str, body: str) -> None:
        stub = self.stub / name
        stub.write_text(f"#!/bin/bash\n{body}\n")
        stub.chmod(0o755)

    def run(self) -> subprocess.CompletedProcess:
        """Execute the real generated script under the stub environment."""
        script = sprite_service._seed_script("test-key")
        return subprocess.run(
            ["bash", "-c", script],
            env={"HOME": str(self.home), "PATH": str(self.stub)},
            capture_output=True,
            text=True,
            timeout=60,
        )

    def calls(self) -> str:
        return self.calls_log.read_text() if self.calls_log.exists() else ""

    def npm_calls(self) -> list[str]:
        return self.npm_log.read_text().splitlines() if self.npm_log.exists() else []


def test_missing_npm_fails_seed_with_precise_message(tmp_path, monkeypatch):
    """The acceptance condition: a box without npm gets a diagnosable failure
    (exit 1, self-describing stderr) at the pi line — the seed stops there,
    and nothing after it (config, plugins, skills) runs."""
    env = _SeedEnv(tmp_path, monkeypatch, with_npm=False, with_pi=False)
    result = env.run()

    assert result.returncode == 1  # a clean guard failure, not 127
    assert "npm is not present on this sprite base image" in result.stderr
    assert f"@earendil-works/pi-coding-agent@{sprite_service.PI_VERSION}" in result.stderr
    assert not (env.home / ".stash" / "config.json").exists()
    assert "stash skills sync" not in env.calls()


def test_npm_present_installs_pinned_pi(tmp_path, monkeypatch):
    env = _SeedEnv(tmp_path, monkeypatch, with_npm=True, with_pi=False)
    result = env.run()

    assert result.returncode == 0, result.stderr
    assert env.npm_calls() == [
        f"npm install -g --ignore-scripts @earendil-works/pi-coding-agent"
        f"@{sprite_service.PI_VERSION}",
        "npm prefix -g",
    ]
    link = env.home / ".local" / "bin" / "pi"
    assert link.is_symlink()
    assert os.readlink(link) == str(env.prefix / "bin" / "pi")
    assert '"test-key"' in (env.home / ".stash" / "config.json").read_text()
    calls = env.calls()
    assert "claude plugin marketplace add Fergana-Labs/stash" in calls
    assert "claude plugin install stash@stash-plugins" in calls
    assert "stash skills sync" in calls
    assert "opencode" not in calls  # stub on PATH -> the curl branch never ran


def test_pi_already_installed_is_idempotent_noop(tmp_path, monkeypatch):
    """Reseeding an already-seeded box never enters the install: npm is not
    even invoked, so a box whose npm vanished later still reseeds cleanly."""
    env = _SeedEnv(tmp_path, monkeypatch, with_npm=True, with_pi=True)
    result = env.run()

    assert result.returncode == 0, result.stderr
    assert env.npm_calls() == []


def test_seed_version_bumped_past_pi_seed():
    """STAS-098 shipped the pi seed line at version 3; the npm guard must
    push every existing box through the hardened seed once."""
    assert sprite_service.SEED_VERSION > 3


def test_guard_message_interpolates_pinned_version():
    """The generated script carries the guard with the pinned package name
    and version, and the old unguarded one-liner is gone."""
    script = sprite_service._seed_script("test-key")
    assert "npm is not present on this sprite base image" in script
    assert f"@earendil-works/pi-coding-agent@{sprite_service.PI_VERSION}" in script
    assert "command -v pi > /dev/null || install_pi" in script
    assert "command -v pi > /dev/null || {" not in script
