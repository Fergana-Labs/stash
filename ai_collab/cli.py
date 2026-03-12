"""Click CLI for ai-collab: init, record, serve, setup-db, status."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import click

from . import db, git_utils
from .capture import record_from_stdin
from .mcp_server import run_server


@click.group()
def cli() -> None:
    """ai-collab: Collaborative AI session history for Boozle."""
    pass


@cli.command("setup-db")
def setup_db() -> None:
    """Create tables in the Neon PostgreSQL database (idempotent)."""
    from .config import settings

    if not settings.DATABASE_URL:
        click.echo("Error: AI_COLLAB_DATABASE_URL is not set.", err=True)
        raise SystemExit(1)
    click.echo("Creating ai-collab tables...")
    db.setup_tables()
    click.echo("Done. Tables created successfully.")


@cli.command()
def record() -> None:
    """Hook handler — reads JSON from stdin and records to database."""
    record_from_stdin()


@cli.command()
def serve() -> None:
    """Start the MCP stdio server."""
    run_server()


@cli.command()
def init() -> None:
    """Configure Claude Code hooks and MCP for this repo."""
    repo_root = _find_repo_root()
    if not repo_root:
        click.echo("Error: not inside a git repository.", err=True)
        raise SystemExit(1)

    _setup_hooks(repo_root)
    _setup_mcp(repo_root)
    click.echo("ai-collab initialized successfully.")


@cli.command()
@click.option("--limit", "-n", default=10, help="Number of sessions to show.")
def status(limit: int) -> None:
    """Show recent AI sessions for this repository."""
    from .config import settings

    if not settings.DATABASE_URL:
        click.echo("Error: AI_COLLAB_DATABASE_URL is not set.", err=True)
        raise SystemExit(1)

    repo_url = git_utils.remote_url()
    if not repo_url:
        click.echo("Error: could not determine git remote URL.", err=True)
        raise SystemExit(1)

    sessions = db.recent_sessions(repo_url=repo_url, limit=limit)
    if not sessions:
        click.echo("No AI sessions recorded for this repository.")
        return

    click.echo(f"Recent AI sessions ({len(sessions)}):\n")
    for s in sessions:
        ended = s.get("ended_at") or "active"
        click.echo(
            f"  [{s['id'][:8]}] {s['user_name']} on {s.get('branch', '?')}\n"
            f"    started: {s['started_at']}  ended: {ended}\n"
            f"    sha: {s.get('head_sha_start', '?')[:8]}..{(s.get('head_sha_end') or '?')[:8]}\n"
        )

    total = db.session_count(repo_url)
    click.echo(f"Total sessions recorded: {total}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path | None:
    root = git_utils._run(["rev-parse", "--show-toplevel"])
    return Path(root) if root else None


def _cli_bin() -> str:
    """Resolve the absolute path to the ai-collab binary."""
    # Prefer the binary next to the current Python interpreter
    bin_dir = Path(sys.executable).parent
    candidate = bin_dir / "ai-collab"
    if candidate.exists():
        return str(candidate)
    # Fall back to PATH lookup
    found = shutil.which("ai-collab")
    return found or "ai-collab"


def _setup_hooks(repo_root: Path) -> None:
    """Write Claude Code hooks to .claude/settings.json."""
    claude_dir = repo_root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"

    # Load existing or create new
    if settings_path.exists():
        with open(settings_path) as f:
            config = json.load(f)
    else:
        config = {}

    hooks = config.setdefault("hooks", {})
    record_cmd = f"{_cli_bin()} record"

    hooks["SessionStart"] = [
        {"type": "command", "command": record_cmd, "blocking": True}
    ]
    hooks["UserPromptSubmit"] = [
        {"type": "command", "command": record_cmd, "blocking": False}
    ]
    hooks["PostToolUse"] = [
        {"type": "command", "command": record_cmd, "blocking": False, "matcher": "Bash|Write|Edit"}
    ]
    hooks["Stop"] = [
        {"type": "command", "command": record_cmd, "blocking": False}
    ]

    with open(settings_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    click.echo(f"  Hooks configured in {settings_path}")


def _setup_mcp(repo_root: Path) -> None:
    """Add ai-collab stdio server to root .mcp.json."""
    mcp_path = repo_root / ".mcp.json"

    if mcp_path.exists():
        with open(mcp_path) as f:
            config = json.load(f)
    else:
        config = {}

    servers = config.setdefault("mcpServers", {})
    servers["ai-collab"] = {
        "type": "stdio",
        "command": _cli_bin(),
        "args": ["serve"],
    }

    with open(mcp_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    click.echo(f"  MCP server added to {mcp_path}")


if __name__ == "__main__":
    cli()
