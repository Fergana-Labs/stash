"""Boozle CLI — command-line interface for moltchat (new workspace model)."""

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


def _default_workspace() -> str:
    cfg = load_config()
    ws = cfg.get("default_workspace", "")
    if not ws:
        console.print("[red]No default workspace. Set with: boozle config default_workspace <id>[/red]")
        raise typer.Exit(1)
    return ws


def _default_chat() -> str:
    cfg = load_config()
    ch = cfg.get("default_chat", "")
    if not ch:
        console.print("[red]No default chat. Set with: boozle config default_chat <id>[/red]")
        raise typer.Exit(1)
    return ch


def _handle_error(e: BoozleError) -> None:
    console.print(f"[red]Error [{e.status_code}]: {e.detail}[/red]")
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.command()
def register(
    name: str = typer.Argument(...),
    type: str = typer.Option("agent"),
    description: str = typer.Option(""),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create account and store API key."""
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


@app.command()
def login(
    name: str = typer.Argument(...),
    password: str = typer.Option(..., prompt=True, hide_input=True),
    as_json: bool = typer.Option(False, "--json"),
):
    """Login with password."""
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


@app.command()
def auth(
    base_url: str = typer.Argument(...),
    api_key: str = typer.Option(..., "--api-key"),
):
    """Store existing credentials."""
    save_config(base_url=base_url, api_key=api_key)
    with BoozleClient(base_url=base_url, api_key=api_key) as c:
        try:
            user = c.whoami()
            save_config(username=user["name"])
            console.print(f"[green]Authenticated as {user['name']}[/green]")
        except BoozleError:
            console.print("[yellow]Saved but could not verify.[/yellow]")


@app.command()
def whoami(as_json: bool = typer.Option(False, "--json")):
    """Show profile."""
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
# Workspaces
# ---------------------------------------------------------------------------

ws_app = typer.Typer(help="Workspace management.")
app.add_typer(ws_app, name="workspaces")


@ws_app.command("list")
def ws_list(mine: bool = typer.Option(False, "--mine"), as_json: bool = typer.Option(False, "--json")):
    """List workspaces."""
    with _client() as c:
        try:
            data = c.list_workspaces(mine=mine)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_rooms(data, title="My Workspaces" if mine else "Public Workspaces")


@ws_app.command("create")
def ws_create(name: str = typer.Argument(...), description: str = typer.Option(""), public: bool = typer.Option(False, "--public"), as_json: bool = typer.Option(False, "--json")):
    """Create workspace."""
    with _client() as c:
        try:
            data = c.create_workspace(name, description=description, is_public=public)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Created '{data['name']}'[/green]  ID: {data['id']}  Invite: {data['invite_code']}")


@ws_app.command("join")
def ws_join(invite_code: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Join workspace by invite code."""
    with _client() as c:
        try:
            data = c.join_workspace(invite_code)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Joined '{data.get('name', 'workspace')}'[/green]")


@ws_app.command("info")
def ws_info(workspace_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Show workspace details."""
    with _client() as c:
        try:
            data = c.get_workspace(workspace_id)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[bold]{data['name']}[/bold]  Members: {data.get('member_count', '?')}  Public: {data['is_public']}")
        console.print(f"ID: {data['id']}  Invite: {data['invite_code']}")


@ws_app.command("members")
def ws_members(workspace_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """List workspace members."""
    with _client() as c:
        try:
            data = c.workspace_members(workspace_id)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_members(data)


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

chats_app = typer.Typer(help="Chat channels.")
app.add_typer(chats_app, name="chats")


@chats_app.command("list")
def chats_list(workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")):
    """List chats in a workspace."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            data = c.list_chats(ws)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No chats.[/dim]")
        else:
            for ch in data:
                console.print(f"  {ch['name']}  (id: {str(ch['id'])[:8]})")


@chats_app.command("create")
def chats_create(name: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), description: str = typer.Option(""), as_json: bool = typer.Option(False, "--json")):
    """Create a chat channel."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            data = c.create_chat(ws, name, description=description)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Chat '{data['name']}' created.[/green]  ID: {data['id']}")


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

@app.command()
def send(
    message: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    chat_id: str = typer.Option(None, "--chat"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Send a message to a chat."""
    ws = workspace_id or _default_workspace()
    ch = chat_id or _default_chat()
    with _client() as c:
        try:
            data = c.send_message(ws, ch, message)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Sent.[/green]")


@app.command()
def read(
    workspace_id: str = typer.Option(None, "--ws"),
    chat_id: str = typer.Option(None, "--chat"),
    limit: int = typer.Option(50, "-n", "--limit"),
    after: Optional[str] = typer.Option(None, "--after"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Read messages from a chat."""
    ws = workspace_id or _default_workspace()
    ch = chat_id or _default_chat()
    with _client() as c:
        try:
            data = c.read_messages(ws, ch, limit=limit, after=after)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_messages(data)


@app.command()
def search(
    query: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    chat_id: str = typer.Option(None, "--chat"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Search messages in a chat."""
    ws = workspace_id or _default_workspace()
    ch = chat_id or _default_chat()
    with _client() as c:
        try:
            data = c.search_messages(ws, ch, query)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_messages(data)


@app.command()
def dm(
    username: str = typer.Argument(...),
    message: str = typer.Argument(...),
    as_json: bool = typer.Option(False, "--json"),
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
# Memory stores
# ---------------------------------------------------------------------------

memory_app = typer.Typer(help="Memory store management.")
app.add_typer(memory_app, name="memory")


@memory_app.command("list")
def memory_list(workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")):
    """List memory stores."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            data = c.list_memory_stores(ws)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No memory stores.[/dim]")
        else:
            for s in data:
                console.print(f"  {s['name']}  (id: {str(s['id'])[:8]}, events: {s.get('event_count', 0)})")


@memory_app.command("create")
def memory_create(name: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), description: str = typer.Option(""), as_json: bool = typer.Option(False, "--json")):
    """Create a memory store."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            data = c.create_memory_store(ws, name, description=description)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Store '{data['name']}' created.[/green]  ID: {data['id']}")


@memory_app.command("push")
def memory_push(
    content: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    store_id: str = typer.Option(None, "--store"),
    agent_name: str = typer.Option("cli", "--agent"),
    event_type: str = typer.Option("message", "--type"),
    session_id: str = typer.Option(None, "--session"),
    tool_name: str = typer.Option(None, "--tool"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Push an event to a memory store."""
    ws = workspace_id or _default_workspace()
    store = store_id or load_config().get("default_store", "")
    if not store:
        console.print("[red]No store specified. Use --store or set default_store in config.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        try:
            data = c.push_memory_event(
                ws, store, agent_name=agent_name, event_type=event_type,
                content=content, session_id=session_id, tool_name=tool_name,
            )
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Event recorded.[/green]  ID: {data['id']}")


@memory_app.command("query")
def memory_query(
    workspace_id: str = typer.Option(None, "--ws"),
    store_id: str = typer.Option(None, "--store"),
    agent_name: str = typer.Option(None, "--agent"),
    session_id: str = typer.Option(None, "--session"),
    event_type: str = typer.Option(None, "--type"),
    limit: int = typer.Option(50, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Query events from a memory store."""
    ws = workspace_id or _default_workspace()
    store = store_id or load_config().get("default_store", "")
    if not store:
        console.print("[red]No store specified.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        try:
            data = c.query_memory_events(
                ws, store, agent_name=agent_name, session_id=session_id,
                event_type=event_type, limit=limit,
            )
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for e in data:
            tool = f" ({e['tool_name']})" if e.get("tool_name") else ""
            console.print(f"  [{e['created_at'][:19]}] {e['agent_name']}/{e['event_type']}{tool}: {e['content'][:200]}")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    store_id: str = typer.Option(None, "--store"),
    limit: int = typer.Option(50, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Full-text search on memory events."""
    ws = workspace_id or _default_workspace()
    store = store_id or load_config().get("default_store", "")
    if not store:
        console.print("[red]No store specified.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        try:
            data = c.search_memory_events(ws, store, query, limit=limit)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for e in data:
            console.print(f"  [{e['created_at'][:19]}] {e['agent_name']}/{e['event_type']}: {e['content'][:200]}")


# ---------------------------------------------------------------------------
# Agent identities
# ---------------------------------------------------------------------------

agents_app = typer.Typer(help="Manage agent identities.")
app.add_typer(agents_app, name="agents")


@agents_app.command("create")
def agents_create(name: str = typer.Argument(...), display_name: str = typer.Option(""), description: str = typer.Option(""), as_json: bool = typer.Option(False, "--json")):
    """Create agent identity."""
    with _client() as c:
        try:
            data = c.create_agent(name, display_name=display_name, description=description)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Agent '{data['name']}' created.[/green]  API key: [bold]{data['api_key']}[/bold]")


@agents_app.command("list")
def agents_list(as_json: bool = typer.Option(False, "--json")):
    """List your agents."""
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
def agents_rotate_key(agent_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Rotate agent API key."""
    with _client() as c:
        try:
            data = c.rotate_agent_key(agent_id)
        except BoozleError as e:
            _handle_error(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]New key: [bold]{data['api_key']}[/bold][/green]")


@agents_app.command("delete")
def agents_delete(agent_id: str = typer.Argument(...), confirm: bool = typer.Option(False, "--yes", "-y")):
    """Delete agent."""
    if not confirm:
        typer.confirm(f"Delete agent {agent_id}?", abort=True)
    with _client() as c:
        try:
            c.delete_agent(agent_id)
        except BoozleError as e:
            _handle_error(e)
    console.print("[green]Deleted.[/green]")


# ---------------------------------------------------------------------------
# Poll + Notify
# ---------------------------------------------------------------------------

@app.command()
def poll(
    workspace_id: str = typer.Option(None, "--ws"),
    chat_id: str = typer.Option(None, "--chat"),
    interval: int = typer.Option(5, "-i", "--interval"),
):
    """Poll for new messages. JSON lines to stdout."""
    ws = workspace_id or _default_workspace()
    ch = chat_id or _default_chat()
    last_ts = None
    with _client() as c:
        try:
            msgs = c.read_messages(ws, ch, limit=1)
            if msgs:
                last_ts = msgs[-1].get("created_at")
        except BoozleError:
            pass
        console.print(f"[dim]Polling... (Ctrl+C to stop)[/dim]", stderr=True)
        try:
            while True:
                time.sleep(interval)
                try:
                    msgs = c.read_messages(ws, ch, limit=50, after=last_ts)
                except BoozleError:
                    continue
                cfg = load_config()
                for msg in msgs:
                    last_ts = msg.get("created_at", last_ts)
                    if msg.get("sender_name") == cfg.get("username"):
                        continue
                    print(json.dumps(msg, default=str), flush=True)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped.[/dim]", stderr=True)


notify_app = typer.Typer(help="Notification subscriptions.")
app.add_typer(notify_app, name="notify")


@notify_app.command("on")
def notify_on(room_id: str = typer.Argument(...)):
    """Subscribe to notifications."""
    add_notify_room(room_id)
    console.print(f"[green]Subscribed.[/green]")


@notify_app.command("off")
def notify_off(room_id: str = typer.Argument(...)):
    """Unsubscribe."""
    remove_notify_room(room_id)
    console.print(f"[yellow]Unsubscribed.[/yellow]")


@notify_app.command("list")
def notify_list():
    """Show subscriptions."""
    rooms = get_notify_rooms()
    if not rooms:
        console.print("[dim]None.[/dim]")
    else:
        for r in rooms:
            console.print(f"  - {r}")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@app.command("config")
def config_cmd(
    key: Optional[str] = typer.Argument(None),
    value: Optional[str] = typer.Argument(None),
):
    """Show or set config. Keys: base_url, default_workspace, default_chat, default_store, output_format."""
    if key and value:
        cfg = load_config()
        cfg[key] = value
        save_config(**{k: v for k, v in cfg.items() if k in [
            "base_url", "api_key", "username", "default_workspace", "default_chat",
            "default_store", "output_format",
        ]})
        console.print(f"[green]{key} = {value}[/green]")
    else:
        cfg = load_config()
        display = dict(cfg)
        if display.get("api_key"):
            display["api_key"] = display["api_key"][:10] + "..."
        console.print(json.dumps(display, indent=2, default=str))


if __name__ == "__main__":
    app()
