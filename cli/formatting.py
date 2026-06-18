"""Rich output formatting for the stash CLI."""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel

console = Console()


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
