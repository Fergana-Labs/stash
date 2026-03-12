"""Git subprocess helpers for ai-collab."""

import subprocess


def _run(args: list[str]) -> str:
    """Run a git command and return stripped stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def head_sha() -> str:
    return _run(["rev-parse", "HEAD"])


def branch() -> str:
    return _run(["rev-parse", "--abbrev-ref", "HEAD"])


def remote_url() -> str:
    return _run(["remote", "get-url", "origin"])


def is_ancestor(sha: str, ref: str = "HEAD") -> bool:
    """Check if sha is an ancestor of ref."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, ref],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def user_name() -> str:
    return _run(["config", "user.name"]) or "unknown"
