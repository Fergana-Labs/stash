"""Rich output formatting for the stash CLI."""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel

console = Console()
console_err = Console(stderr=True)


def print_empty_state(kind: str) -> None:
    """Emit the one canonical AXI §5 empty-state line on stderr.

    Every list/status command renders `No {kind} found.` (dim-styled) to
    stderr when its data is empty — stderr carries human diagnostics while
    stdout stays reserved for data. This helper is the single source of truth
    for the empty-state message; commands must route every empty branch
    through it rather than printing their own wording.
    """
    console_err.print(f"[dim]No {kind} found.[/dim]")


# Stderr/stdout channel discipline: stdout carries only parseable data;
# all human-readable progress/status/warning/error output goes to stderr so
# agent consumers can parse stdout reliably. echo_stdout/echo_stderr/echo_error
# are the routing helpers; set_progress_suppressed() is the seam STAS-060's
# --json mode toggles to quiet non-error progress while keeping errors.
_err_console = Console(stderr=True)
_out_console = Console()

_suppress_progress = False


def set_progress_suppressed(suppressed: bool) -> None:
    """Suppress non-error progress/status/warning output on stderr."""
    global _suppress_progress
    _suppress_progress = suppressed


def echo_stdout(message: str) -> None:
    """Emit parseable data to stdout only. Never suppressed.

    Parseable data must arrive byte-for-byte intact, so wrapping and Rich
    markup interpretation are switched off here: a wrapped line would corrupt a
    JSON payload a hook runner reads back from stdout.
    """
    _out_console.print(message, soft_wrap=True, markup=False)


def echo_stderr(message: str) -> None:
    """Emit progress/status/warning to stderr. Suppressed by set_progress_suppressed()."""
    if _suppress_progress:
        return
    _err_console.print(message)


def echo_error(message: str) -> None:
    """Emit an error to stderr. Never suppressed. Errors always surface."""
    _err_console.print(f"[red]{message}[/red]")


def output_json(data) -> None:
    """Print data as JSON for machine consumption."""
    print(json.dumps(data, default=str))


def format_message(msg: dict) -> str:
    """Format a single message for display."""
    sender = msg.get("sender_name", msg.get("name", "?"))
    sender_type = msg.get("sender_type", "")
    content = msg.get("content", "")
    ts = msg.get("created_at", "")
    if isinstance(ts, str) and len(ts) > 19:
        ts = ts[:19]
    tag = f" [{sender_type}]" if sender_type == "agent" else ""
    return f"[dim]{ts}[/dim] [bold]{sender}{tag}[/bold]: {content}"


def print_messages(messages: list[dict]) -> None:
    """Print a list of messages."""
    if not messages:
        console.print("[dim]No messages.[/dim]")
        return
    for msg in messages:
        console.print(format_message(msg))


def print_user(user: dict, title: str = "Profile") -> None:
    """Print user profile as a panel."""
    lines = [
        f"[bold]{user.get('name', '')}[/bold]",
        f"Display: {user.get('display_name', '')}",
        f"ID: {user.get('id', '')}",
    ]
    if user.get("description"):
        lines.append(f"Bio: {user['description']}")
    lines.append(f"Created: {user.get('created_at', '')}")
    lines.append(f"Last seen: {user.get('last_seen', '')}")
    console.print(Panel("\n".join(lines), title=title))
