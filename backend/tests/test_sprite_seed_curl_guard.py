"""Hermetic execution of the real generated sprite seed script.

The exact bytes of ``_seed_script`` run under a stub PATH (fake
stash/claude/opencode/curl executables plus symlinked coreutils), so the
curl/opencode orderings are locked exactly as a box would see them:

- curl missing    -> the seed fails with a precise, self-describing message
  (exit 1), not a bare "curl: command not found" (exit 127);
- curl present    -> the pinned opencode install with the exact curl
  arguments;
- opencode present -> idempotent no-op, curl never invoked.

This file is a deliberate sibling of test_sprite_seed_pi_guard.py: it carries
its own _SeedEnv (not an import) because the two files lock independent
orderings of the same generated script. The pi stub is armed by default, so
the unrelated pi line is an idempotent no-op and no npm stub is ever needed.

The stub PATH is the *only* PATH (no /usr/bin:/bin tail): dev machines carry
/usr/bin/curl, which would make the missing-curl case untestable. Everything
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

    def __init__(
        self,
        tmp_path: Path,
        monkeypatch,
        *,
        with_curl: bool,
        with_opencode: bool,
        with_pi: bool = True,
    ):
        self.stub = tmp_path / "stub-bin"
        self.stub.mkdir()
        for real in _COREUTILS:
            (self.stub / real).symlink_to(Path(shutil.which(real)).resolve())

        self.home = tmp_path / "home"
        self.home.mkdir()
        self.workdir = tmp_path / "work"

        self.calls_log = tmp_path / "calls.log"
        self.curl_log = tmp_path / "curl-calls.log"

        # Recorded no-ops: each stub is found on PATH, so its install branch
        # in the seed never runs, and every call lands in calls.log.
        for name in ("stash", "claude"):
            self._write_stub(name, f'echo "{name} $*" >> "{self.calls_log}"')
        if with_opencode:
            self._write_stub("opencode", "exit 0")
        if with_curl:
            # Logs its args, then cats a fake installer to stdout so the
            # seed's `| VERSION=... bash` pipe really executes it. The
            # installer writes the two-line stub opencode (shebang, exit 0)
            # where the real one would land.
            self._write_stub(
                "curl",
                f'echo "curl $*" >> "{self.curl_log}"\n'
                "cat << 'FAKE_INSTALLER'\n"
                'mkdir -p "$HOME/.opencode/bin"\n'
                "printf '%s\\n' '#!/bin/bash' 'exit 0' > \"$HOME/.opencode/bin/opencode\"\n"
                "FAKE_INSTALLER",
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

    def curl_calls(self) -> list[str]:
        return self.curl_log.read_text().splitlines() if self.curl_log.exists() else []


def test_missing_curl_fails_seed_with_precise_message(tmp_path, monkeypatch):
    """The acceptance condition: a box without curl gets a diagnosable
    failure (exit 1, self-describing stderr) at the opencode line — the seed
    stops there, and nothing after it (config, plugins, skills) runs."""
    env = _SeedEnv(tmp_path, monkeypatch, with_curl=False, with_opencode=False)
    result = env.run()

    assert result.returncode == 1  # a clean guard failure, not 127
    assert "curl is not present on this sprite base image" in result.stderr
    assert sprite_service.OPENCODE_VERSION in result.stderr
    assert not (env.home / ".stash" / "config.json").exists()
    assert "stash skills sync" not in env.calls()
    assert not (env.home / ".local" / "bin" / "opencode").exists()


def test_curl_present_installs_pinned_opencode(tmp_path, monkeypatch):
    env = _SeedEnv(tmp_path, monkeypatch, with_curl=True, with_opencode=False)
    result = env.run()

    assert result.returncode == 0, result.stderr
    assert "curl -fsSL https://opencode.ai/install" in env.curl_calls()
    installed = env.home / ".opencode" / "bin" / "opencode"
    assert installed.read_text() == "#!/bin/bash\nexit 0\n"  # the fake installer ran
    link = env.home / ".local" / "bin" / "opencode"
    assert link.is_symlink()
    assert os.readlink(link) == str(installed)
    assert '"test-key"' in (env.home / ".stash" / "config.json").read_text()
    calls = env.calls()
    assert "claude plugin marketplace add Fergana-Labs/stash" in calls
    assert "claude plugin install stash@stash-plugins" in calls
    assert "stash skills sync" in calls


def test_opencode_already_installed_is_idempotent_noop(tmp_path, monkeypatch):
    """Reseeding an already-seeded box never enters the install: curl is not
    even on the PATH, so a box that already has opencode never needs curl."""
    env = _SeedEnv(tmp_path, monkeypatch, with_curl=False, with_opencode=True)
    result = env.run()

    assert result.returncode == 0, result.stderr
    assert env.curl_calls() == []  # curl never invoked
    assert not (env.home / ".opencode").exists()  # installer never ran
    assert (env.home / ".stash" / "config.json").exists()
    assert "stash skills sync" in env.calls()


def test_seed_version_bumped_past_npm_guard():
    """STAS-107 shipped the npm guard at version 4; the curl guard must push
    every existing box through the hardened seed once."""
    assert sprite_service.SEED_VERSION > 4


def test_guard_message_interpolates_pinned_version():
    """The generated script carries the guard with the pinned version, the
    conditional install call, and the old unguarded one-liner is gone."""
    script = sprite_service._seed_script("test-key")
    assert "curl is not present on this sprite base image" in script
    assert f"VERSION={sprite_service.OPENCODE_VERSION} bash" in script
    assert "command -v opencode > /dev/null || install_opencode" in script
    assert "command -v opencode > /dev/null || {" not in script
