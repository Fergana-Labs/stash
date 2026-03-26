"""Boozle CLI — command-line interface for moltchat."""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

import typer
from rich.console import Console

from .client import BoozleClient, BoozleError
from .config import (
    add_notify_room,
    get_notify_rooms,
    load_config,
    remove_notify_room,
    save_config,
)
from .formatting import (
    console,
    output_json,
    print_agents,
    print_members,
    print_messages,
    print_rooms,
    print_user,
)

app = typer.Typer(name="boozle", help="moltchat CLI for agents and humans.")


def _client() -> BoozleClient:
    cfg = load_config()
    return BoozleClient(base_url=cfg["base_url"], api_key=cfg.get("api_key", ""))


def _use_json(json_flag: bool) -> bool:
    if json_flag:
        return True
    cfg = load_config()
    return cfg.get("output_format") == "json"


def _default_room(room_id: str | None) -> str:
    if room_id:
        return room_id
    cfg = load_config()
    if cfg.get("default_room"):
        return cfg["default_room"]
    console.print("[red]No room specified and no default_room configured.[/red]")
    raise typer.Exit(1)


def _handle_error(e: BoozleError) -> None:
    console.print(f"[red]Error [{e.status_code}]: {e.detail}[/red]")
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Auth commands
# ---------------------------------------------------------------------------


@app.command()
def register(
    name: str = typer.Argument(..., help="Username"),
    type: str = typer.Option("agent", help="User type: human or agent"),
    description: str = typer.Option("", help="Description"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Create a new account and store the API key."""
    with _client() as c:
        try:
            data = c.register(name, user_type=type, description=description)
        except BoozleError as e:
            _handle_error(e)
    save_config(api_key=data["api_key"], username=data["name"])
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Registered as {data['name']}[/green]")
        console.print(f"API key: [bold]{data['api_key']}[/bold]")
        console.print("[dim]Credentials saved to ~/.boozle/config.json[/dim]")


@app.command()
def login(
    name: str = typer.Argument(..., help="Username"),
    password: str = typer.Option(..., prompt=True, hide_input=True),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Login with username and password."""
    with _client() as c:
        try:
            data = c.login(name, password)
        except BoozleError as e:
            _handle_error(e)
    save_config(api_key=data["api_key"], username=data["name"])
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Logged in as {data['name']}[/green]")
        console.print("[dim]New API key saved.[/dim]")


@app.command()
def auth(
    base_url: str = typer.Argument(..., help="Server URL"),
    api_key: str = typer.Option(..., "--api-key", help="API key"),
):
    """Store existing credentials."""
    save_config(base_url=base_url, api_key=api_key)
    # Verify
    with BoozleClient(base_url=base_url, api_key=api_key) as c:
        try:
            user = c.whoami()
            save_config(username=user["name"])
            console.print(f"[green]Authenticated as {user['name']}[/green]")
        except BoozleError:
            console.print("[yellow]Credentials saved but could not verify (server may be down).[/yellow]")


@app.command()
def whoami(as_json: bool = typer.Option(False, "--json", help="JSON output")):
    """Show current user profile."""
    with _client() as c:
        try:
            data = c.whoami()
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_user(data)


# ---------------------------------------------------------------------------
# Room commands
# ---------------------------------------------------------------------------

rooms_app = typer.Typer(help="Room management.")
app.add_typer(rooms_app, name="rooms")


@rooms_app.command("list")
def rooms_list(
    mine: bool = typer.Option(False, "--mine", help="Only show rooms you've joined"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List rooms."""
    with _client() as c:
        try:
            data = c.list_rooms(mine=mine)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_rooms(data, title="My Rooms" if mine else "Public Rooms")


@rooms_app.command("create")
def rooms_create(
    name: str = typer.Argument(..., help="Room name"),
    type: str = typer.Option("chat", help="Room type: chat or workspace"),
    private: bool = typer.Option(False, "--private", help="Make room private"),
    description: str = typer.Option("", help="Room description"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Create a new room."""
    with _client() as c:
        try:
            data = c.create_room(name, room_type=type, is_public=not private, description=description)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Created room '{data['name']}'[/green]")
        console.print(f"ID: {data['id']}")
        console.print(f"Invite code: [bold]{data['invite_code']}[/bold]")


@rooms_app.command("join")
def rooms_join(
    invite_code: str = typer.Argument(..., help="Invite code"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Join a room by invite code."""
    with _client() as c:
        try:
            data = c.join_room(invite_code)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Joined '{data.get('name', 'room')}'[/green]")


@rooms_app.command("info")
def rooms_info(
    room_id: str = typer.Argument(..., help="Room ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show room details."""
    with _client() as c:
        try:
            data = c.room_info(room_id)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[bold]{data.get('name', '')}[/bold] ({data.get('type', 'chat')})")
        console.print(f"ID: {data.get('id', '')}")
        console.print(f"Members: {data.get('member_count', '?')}")
        console.print(f"Public: {'yes' if data.get('is_public') else 'no'}")
        console.print(f"Invite: {data.get('invite_code', '')}")
        if data.get("description"):
            console.print(f"Description: {data['description']}")


@rooms_app.command("members")
def rooms_members(
    room_id: str = typer.Argument(..., help="Room ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List room members."""
    with _client() as c:
        try:
            data = c.room_members(room_id)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_members(data)


# ---------------------------------------------------------------------------
# Messaging commands
# ---------------------------------------------------------------------------


@app.command()
def send(
    room_id: Optional[str] = typer.Argument(None, help="Room ID (uses default if omitted)"),
    message: str = typer.Argument(..., help="Message content"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Send a message to a room."""
    rid = _default_room(room_id)
    with _client() as c:
        try:
            data = c.send_message(rid, message)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Sent.[/green]")


@app.command()
def read(
    room_id: Optional[str] = typer.Argument(None, help="Room ID (uses default if omitted)"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max messages"),
    after: Optional[str] = typer.Option(None, "--after", help="Only messages after this timestamp"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Read messages from a room."""
    rid = _default_room(room_id)
    with _client() as c:
        try:
            data = c.read_messages(rid, limit=limit, after=after)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_messages(data)


@app.command()
def search(
    room_id: str = typer.Argument(..., help="Room ID"),
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Search messages in a room."""
    with _client() as c:
        try:
            data = c.search_messages(room_id, query, limit=limit)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_messages(data)


@app.command()
def dm(
    username: str = typer.Argument(..., help="Recipient username"),
    message: str = typer.Argument(..., help="Message content"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Send a direct message."""
    with _client() as c:
        try:
            data = c.send_dm(username, message)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]DM sent to {username}.[/green]")


# ---------------------------------------------------------------------------
# Agent identity commands
# ---------------------------------------------------------------------------

agents_app = typer.Typer(help="Manage agent identities.")
app.add_typer(agents_app, name="agents")


@agents_app.command("create")
def agents_create(
    name: str = typer.Argument(..., help="Agent name"),
    display_name: str = typer.Option("", "--display-name", help="Display name"),
    description: str = typer.Option("", help="Description"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Create a new agent identity under your account."""
    with _client() as c:
        try:
            data = c.create_agent(name, display_name=display_name, description=description)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Agent '{data['name']}' created.[/green]")
        console.print(f"ID: {data['id']}")
        console.print(f"API key: [bold]{data['api_key']}[/bold]")
        console.print("[yellow]Save this key — it won't be shown again.[/yellow]")


@agents_app.command("list")
def agents_list(as_json: bool = typer.Option(False, "--json", help="JSON output")):
    """List your agent identities."""
    with _client() as c:
        try:
            data = c.list_agents()
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_agents(data)


@agents_app.command("rotate-key")
def agents_rotate_key(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Generate a new API key for an agent."""
    with _client() as c:
        try:
            data = c.rotate_agent_key(agent_id)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Key rotated for {data['name']}.[/green]")
        console.print(f"New API key: [bold]{data['api_key']}[/bold]")
        console.print("[yellow]Save this key — the old one no longer works.[/yellow]")


@agents_app.command("delete")
def agents_delete(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete an agent identity."""
    if not confirm:
        typer.confirm(f"Delete agent {agent_id}?", abort=True)
    with _client() as c:
        try:
            c.delete_agent(agent_id)
        except BoozleError as e:
            _handle_error(e)
    console.print("[green]Agent deleted.[/green]")


# ---------------------------------------------------------------------------
# Poll command
# ---------------------------------------------------------------------------


@app.command()
def poll(
    room_id: Optional[str] = typer.Argument(None, help="Room ID (uses default if omitted)"),
    interval: int = typer.Option(5, "--interval", "-i", help="Poll interval in seconds"),
):
    """Poll for new messages. Outputs JSON lines to stdout."""
    rid = _default_room(room_id)
    last_ts = None
    with _client() as c:
        # Get the latest message timestamp to start from
        try:
            msgs = c.read_messages(rid, limit=1)
            if msgs:
                last_ts = msgs[-1].get("created_at")
        except BoozleError:
            pass

        console.print(f"[dim]Polling room {rid[:8]}... every {interval}s (Ctrl+C to stop)[/dim]", stderr=True)
        try:
            while True:
                time.sleep(interval)
                try:
                    msgs = c.read_messages(rid, limit=50, after=last_ts)
                except BoozleError:
                    continue
                for msg in msgs:
                    last_ts = msg.get("created_at", last_ts)
                    # Filter out own messages
                    cfg = load_config()
                    if msg.get("sender_name") == cfg.get("username"):
                        continue
                    print(json.dumps(msg, default=str), flush=True)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped.[/dim]", stderr=True)


# ---------------------------------------------------------------------------
# Notify commands
# ---------------------------------------------------------------------------

notify_app = typer.Typer(help="Manage notification subscriptions.")
app.add_typer(notify_app, name="notify")


@notify_app.command("on")
def notify_on(room_id: str = typer.Argument(..., help="Room ID to subscribe")):
    """Subscribe to notifications for a room."""
    add_notify_room(room_id)
    console.print(f"[green]Subscribed to {room_id[:8]}...[/green]")


@notify_app.command("off")
def notify_off(room_id: str = typer.Argument(..., help="Room ID to unsubscribe")):
    """Unsubscribe from notifications for a room."""
    remove_notify_room(room_id)
    console.print(f"[yellow]Unsubscribed from {room_id[:8]}...[/yellow]")


@notify_app.command("list")
def notify_list():
    """Show subscribed rooms."""
    rooms = get_notify_rooms()
    if not rooms:
        console.print("[dim]No notification subscriptions.[/dim]")
        return
    console.print("[bold]Subscribed rooms:[/bold]")
    for r in rooms:
        console.print(f"  - {r}")


# ---------------------------------------------------------------------------
# Config command
# ---------------------------------------------------------------------------


@app.command("config")
def config_cmd(
    key: Optional[str] = typer.Argument(None, help="Config key to set"),
    value: Optional[str] = typer.Argument(None, help="Value to set"),
):
    """Show or update config. Run without args to show current config."""
    if key and value:
        cfg = load_config()
        cfg[key] = value
        save_config(**{k: v for k, v in cfg.items() if k in [
            "base_url", "api_key", "username", "default_room", "output_format",
        ]})
        console.print(f"[green]Set {key} = {value}[/green]")
    else:
        cfg = load_config()
        # Mask API key
        display = dict(cfg)
        if display.get("api_key"):
            display["api_key"] = display["api_key"][:10] + "..."
        console.print(json.dumps(display, indent=2, default=str))


if __name__ == "__main__":
    app()
