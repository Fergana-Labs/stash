"""Rich output formatting for the octopus CLI."""

from __future__ import annotations

import json
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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


def print_rooms(rooms: list[dict], title: str = "Rooms") -> None:
    """Print a table of rooms."""
    if not rooms:
        console.print("[dim]No rooms found.[/dim]")
        return
    table = Table(title=title)
    table.add_column("Name", style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Type")
    table.add_column("Members")
    table.add_column("Public")
    for r in rooms:
        table.add_row(
            r.get("name", ""),
            str(r.get("id", ""))[:8],
            r.get("type", "chat"),
            str(r.get("member_count", "?")),
            "yes" if r.get("is_public") else "no",
        )
    console.print(table)


def print_user(user: dict, title: str = "Profile") -> None:
    """Print user profile as a panel."""
    lines = [
        f"[bold]{user.get('name', '')}[/bold]",
        f"Display: {user.get('display_name', '')}",
        f"Type: {user.get('type', '')}",
        f"ID: {user.get('id', '')}",
    ]
    if user.get("description"):
        lines.append(f"Bio: {user['description']}")
    if user.get("owner_id"):
        lines.append(f"Owner: {user['owner_id']}")
    lines.append(f"Created: {user.get('created_at', '')}")
    lines.append(f"Last seen: {user.get('last_seen', '')}")
    console.print(Panel("\n".join(lines), title=title))


def print_personas(personas: list[dict]) -> None:
    """Print a table of agent identities."""
    if not personas:
        console.print("[dim]No agent identities. Use 'octopus personas create' to make one.[/dim]")
        return
    table = Table(title="Agent Identities")
    table.add_column("Name", style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Display Name")
    table.add_column("Last Seen")
    for p in personas:
        table.add_row(
            p.get("name", ""),
            str(p.get("id", ""))[:8],
            p.get("display_name", ""),
            str(p.get("last_seen", ""))[:19],
        )
    console.print(table)


def print_members(members: list[dict]) -> None:
    """Print room members table."""
    if not members:
        console.print("[dim]No members.[/dim]")
        return
    table = Table(title="Members")
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Role")
    table.add_column("Joined")
    for m in members:
        table.add_row(
            m.get("name", ""),
            m.get("type", ""),
            m.get("role", "member"),
            str(m.get("joined_at", ""))[:19],
        )
    console.print(table)
