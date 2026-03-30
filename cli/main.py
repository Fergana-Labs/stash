"""Boozle CLI — command-line interface for workspaces, chats, notebooks, history, and decks."""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

import typer

from .client import BoozleClient, BoozleError
from .config import load_config, save_config, add_notify_room, get_notify_rooms, remove_notify_room
from .formatting import console, output_json, print_agents, print_members, print_messages, print_rooms, print_user

app = typer.Typer(name="boozle", help="Boozle CLI — workspaces, chats, notebooks, history, decks.")


def _client() -> BoozleClient:
    cfg = load_config()
    return BoozleClient(base_url=cfg["base_url"], api_key=cfg.get("api_key", ""))


def _use_json(flag: bool) -> bool:
    return flag or load_config().get("output_format") == "json"


def _default_workspace() -> str:
    ws = load_config().get("default_workspace", "")
    if not ws:
        console.print("[red]No default workspace. Set with: boozle config default_workspace <id>[/red]")
        raise typer.Exit(1)
    return ws


def _default_chat() -> str:
    ch = load_config().get("default_chat", "")
    if not ch:
        console.print("[red]No default chat. Set with: boozle config default_chat <id>[/red]")
        raise typer.Exit(1)
    return ch


def _err(e: BoozleError) -> None:
    console.print(f"[red]Error [{e.status_code}]: {e.detail}[/red]")
    raise typer.Exit(1)


# ===========================================================================
# Auth
# ===========================================================================

@app.command()
def register(name: str = typer.Argument(...), type: str = typer.Option("agent"), description: str = typer.Option(""), as_json: bool = typer.Option(False, "--json")):
    """Create account and store API key."""
    with _client() as c:
        try:
            data = c.register(name, user_type=type, description=description)
        except BoozleError as e:
            _err(e)
    save_config(api_key=data["api_key"], username=data["name"])
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Registered as {data['name']}[/green]  API key: [bold]{data['api_key']}[/bold]")


@app.command()
def login(name: str = typer.Argument(...), password: str = typer.Option(..., prompt=True, hide_input=True), as_json: bool = typer.Option(False, "--json")):
    """Login with password."""
    with _client() as c:
        try:
            data = c.login(name, password)
        except BoozleError as e:
            _err(e)
    save_config(api_key=data["api_key"], username=data["name"])
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Logged in as {data['name']}[/green]")


@app.command()
def auth(base_url: str = typer.Argument(...), api_key: str = typer.Option(..., "--api-key")):
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
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_user(data)


# ===========================================================================
# Workspaces
# ===========================================================================

ws_app = typer.Typer(help="Workspace management.")
app.add_typer(ws_app, name="workspaces")


@ws_app.command("list")
def ws_list(mine: bool = typer.Option(False, "--mine"), as_json: bool = typer.Option(False, "--json")):
    """List workspaces."""
    with _client() as c:
        try:
            data = c.list_workspaces(mine=mine)
        except BoozleError as e:
            _err(e)
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
            _err(e)
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
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Joined '{data.get('name')}'[/green]")


@ws_app.command("info")
def ws_info(workspace_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Show workspace details."""
    with _client() as c:
        try:
            data = c.get_workspace(workspace_id)
        except BoozleError as e:
            _err(e)
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
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_members(data)


# ===========================================================================
# Chats
# ===========================================================================

chats_app = typer.Typer(help="Chat channels (workspace + personal rooms + DMs).")
app.add_typer(chats_app, name="chats")


@chats_app.command("list")
def chats_list(workspace_id: str = typer.Option(None, "--ws"), all_: bool = typer.Option(False, "--all"), as_json: bool = typer.Option(False, "--json")):
    """List chats. --all for cross-workspace view, --ws for single workspace."""
    with _client() as c:
        try:
            if all_:
                data = c.all_chats()
                if _use_json(as_json):
                    output_json(data)
                else:
                    chats = data.get("chats", [])
                    dms = data.get("dms", [])
                    if chats:
                        console.print("[bold]Rooms[/bold]")
                        for ch in chats:
                            ws = f" [{ch.get('workspace_name', 'personal')}]" if ch.get("workspace_name") else ""
                            console.print(f"  #{ch['name']}{ws}  (id: {str(ch['id'])[:8]})")
                    if dms:
                        console.print("[bold]DMs[/bold]")
                        for dm in dms:
                            other = dm.get("other_user") or {}
                            console.print(f"  @{other.get('name', '?')}  (id: {str(dm['id'])[:8]})")
                return
            ws = workspace_id or _default_workspace()
            data = c.list_chats(ws)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No chats.[/dim]")
        else:
            for ch in data:
                console.print(f"  #{ch['name']}  (id: {str(ch['id'])[:8]})")


@chats_app.command("create")
def chats_create(name: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), description: str = typer.Option(""), personal: bool = typer.Option(False, "--personal"), as_json: bool = typer.Option(False, "--json")):
    """Create a chat. --personal for personal room, otherwise workspace chat."""
    with _client() as c:
        try:
            if personal:
                data = c.create_room(name, description=description)
            else:
                ws = workspace_id or _default_workspace()
                data = c.create_chat(ws, name, description=description)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Chat '{data['name']}' created.[/green]  ID: {data['id']}")


# ===========================================================================
# Messaging
# ===========================================================================

@app.command()
def send(message: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), chat_id: str = typer.Option(None, "--chat"), room_id: str = typer.Option(None, "--room"), as_json: bool = typer.Option(False, "--json")):
    """Send a message. Use --room for personal rooms, --ws + --chat for workspace chats."""
    with _client() as c:
        try:
            if room_id:
                data = c.send_room_message(room_id, message)
            else:
                ws = workspace_id or _default_workspace()
                ch = chat_id or _default_chat()
                data = c.send_message(ws, ch, message)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Sent.[/green]")


@app.command()
def read(workspace_id: str = typer.Option(None, "--ws"), chat_id: str = typer.Option(None, "--chat"), room_id: str = typer.Option(None, "--room"), dm_id: str = typer.Option(None, "--dm"), limit: int = typer.Option(50, "-n"), after: Optional[str] = typer.Option(None, "--after"), as_json: bool = typer.Option(False, "--json")):
    """Read messages. Use --room, --dm, or --ws + --chat."""
    with _client() as c:
        try:
            if room_id:
                data = c.read_room_messages(room_id, limit=limit, after=after)
            elif dm_id:
                data = c.read_dm_messages(dm_id, limit=limit, after=after)
            else:
                ws = workspace_id or _default_workspace()
                ch = chat_id or _default_chat()
                data = c.read_messages(ws, ch, limit=limit, after=after)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_messages(data)


@app.command()
def dm(username: str = typer.Argument(...), message: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Send a direct message."""
    with _client() as c:
        try:
            data = c.send_dm(username, message)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]DM sent to {username}.[/green]")


@app.command("dms")
def dms_list(as_json: bool = typer.Option(False, "--json")):
    """List DM conversations."""
    with _client() as c:
        try:
            data = c.list_dms()
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No DMs.[/dim]")
        else:
            for d in data:
                other = d.get("other_user") or {}
                console.print(f"  @{other.get('name', '?')}  (id: {str(d['id'])[:8]})")


# ===========================================================================
# Notebooks
# ===========================================================================

nb_app = typer.Typer(help="Notebook collections (folders + markdown pages).")
app.add_typer(nb_app, name="notebooks")


@nb_app.command("list")
def nb_list(workspace_id: str = typer.Option(None, "--ws"), all_: bool = typer.Option(False, "--all"), as_json: bool = typer.Option(False, "--json")):
    """List notebooks. --all for cross-workspace, --ws for single workspace."""
    with _client() as c:
        try:
            data = c.all_notebooks() if all_ else c.list_notebooks(workspace_id or _default_workspace())
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No notebooks.[/dim]")
        else:
            for nb in data:
                ws = f" [{nb.get('workspace_name', '')}]" if nb.get("workspace_name") else ""
                console.print(f"  {nb['name']}{ws}  (id: {str(nb['id'])[:8]})")


@nb_app.command("create")
def nb_create(name: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), description: str = typer.Option(""), personal: bool = typer.Option(False, "--personal"), as_json: bool = typer.Option(False, "--json")):
    """Create a notebook collection."""
    with _client() as c:
        try:
            if personal:
                data = c.create_personal_notebook(name, description=description)
            else:
                ws = workspace_id or _default_workspace()
                data = c.create_notebook(ws, name, description=description)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Notebook '{data['name']}' created.[/green]  ID: {data['id']}")


@nb_app.command("pages")
def nb_pages(notebook_id: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")):
    """List pages in a notebook."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.list_page_tree(ws, notebook_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for folder in data.get("folders", []):
            console.print(f"  [bold]{folder['name']}/[/bold]")
            for f in folder.get("files", []):
                console.print(f"    {f['name']}  (id: {str(f['id'])[:8]})")
        for f in data.get("root_files", []):
            console.print(f"  {f['name']}  (id: {str(f['id'])[:8]})")


@nb_app.command("add-page")
def nb_add_page(notebook_id: str = typer.Argument(...), name: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), content: str = typer.Option(""), as_json: bool = typer.Option(False, "--json")):
    """Add a page to a notebook."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.create_page(ws, notebook_id, name, content=content)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Page '{data['name']}' created.[/green]  ID: {data['id']}")


@nb_app.command("read-page")
def nb_read_page(notebook_id: str = typer.Argument(...), page_id: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")):
    """Read a page's content."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.get_page(ws, notebook_id, page_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[bold]{data['name']}[/bold]\n")
        console.print(data.get("content_markdown", ""))


@nb_app.command("edit-page")
def nb_edit_page(notebook_id: str = typer.Argument(...), page_id: str = typer.Argument(...), content: str = typer.Option(None, "--content"), name: str = typer.Option(None, "--name"), workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")):
    """Update a page. Reads from stdin if --content not given."""
    if content is None and not sys.stdin.isatty():
        content = sys.stdin.read()
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            kwargs = {}
            if content is not None:
                kwargs["content"] = content
            if name is not None:
                kwargs["name"] = name
            data = c.update_page(ws, notebook_id, page_id, **kwargs)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Page updated.[/green]")


# ===========================================================================
# History (was memory stores)
# ===========================================================================

hist_app = typer.Typer(help="History — structured agent event logs.")
app.add_typer(hist_app, name="history")


@hist_app.command("list")
def hist_list(workspace_id: str = typer.Option(None, "--ws"), all_: bool = typer.Option(False, "--all"), as_json: bool = typer.Option(False, "--json")):
    """List history stores."""
    with _client() as c:
        try:
            data = c.all_histories() if all_ else c.list_histories(workspace_id or _default_workspace())
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No history stores.[/dim]")
        else:
            for s in data:
                console.print(f"  {s['name']}  (id: {str(s['id'])[:8]}, events: {s.get('event_count', 0)})")


@hist_app.command("create")
def hist_create(name: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), description: str = typer.Option(""), as_json: bool = typer.Option(False, "--json")):
    """Create a history store."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.create_history(ws, name, description=description)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]History '{data['name']}' created.[/green]  ID: {data['id']}")


@hist_app.command("push")
def hist_push(content: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), store_id: str = typer.Option(None, "--store"), agent_name: str = typer.Option("cli", "--agent"), event_type: str = typer.Option("message", "--type"), session_id: str = typer.Option(None, "--session"), tool_name: str = typer.Option(None, "--tool"), as_json: bool = typer.Option(False, "--json")):
    """Push an event to a history store."""
    ws = workspace_id or _default_workspace()
    store = store_id or load_config().get("default_store", "")
    if not store:
        console.print("[red]No store specified. Use --store or set default_store.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        try:
            data = c.push_event(ws, store, agent_name=agent_name, event_type=event_type, content=content, session_id=session_id, tool_name=tool_name)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Event recorded.[/green]  ID: {data['id']}")


@hist_app.command("query")
def hist_query(workspace_id: str = typer.Option(None, "--ws"), store_id: str = typer.Option(None, "--store"), agent_name: str = typer.Option(None, "--agent"), event_type: str = typer.Option(None, "--type"), limit: int = typer.Option(50, "-n"), all_: bool = typer.Option(False, "--all"), as_json: bool = typer.Option(False, "--json")):
    """Query events. --all for cross-workspace."""
    with _client() as c:
        try:
            if all_:
                data = c.all_events(agent_name=agent_name, event_type=event_type, limit=limit)
            else:
                ws = workspace_id or _default_workspace()
                store = store_id or load_config().get("default_store", "")
                if not store:
                    console.print("[red]No store specified.[/red]")
                    raise typer.Exit(1)
                data = c.query_events(ws, store, agent_name=agent_name, event_type=event_type, limit=limit)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for ev in data:
            tool = f" ({ev['tool_name']})" if ev.get("tool_name") else ""
            console.print(f"  [{ev['created_at'][:19]}] {ev['agent_name']}/{ev['event_type']}{tool}: {ev['content'][:200]}")


@hist_app.command("search")
def hist_search(query: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), store_id: str = typer.Option(None, "--store"), limit: int = typer.Option(50, "-n"), as_json: bool = typer.Option(False, "--json")):
    """Full-text search on events."""
    ws = workspace_id or _default_workspace()
    store = store_id or load_config().get("default_store", "")
    if not store:
        console.print("[red]No store specified.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        try:
            data = c.search_events(ws, store, query, limit=limit)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for ev in data:
            console.print(f"  [{ev['created_at'][:19]}] {ev['agent_name']}/{ev['event_type']}: {ev['content'][:200]}")


# ===========================================================================
# Decks
# ===========================================================================

decks_app = typer.Typer(help="Decks — HTML/JS/CSS documents with public sharing.")
app.add_typer(decks_app, name="decks")


@decks_app.command("list")
def decks_list(workspace_id: str = typer.Option(None, "--ws"), all_: bool = typer.Option(False, "--all"), as_json: bool = typer.Option(False, "--json")):
    """List decks. --all for cross-workspace."""
    with _client() as c:
        try:
            data = c.all_decks() if all_ else c.list_decks(workspace_id or _default_workspace())
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No decks.[/dim]")
        else:
            for d in data:
                ws = f" [{d.get('workspace_name', '')}]" if d.get("workspace_name") else ""
                console.print(f"  {d['name']}{ws}  ({d.get('deck_type', 'freeform')}, id: {str(d['id'])[:8]})")


@decks_app.command("create")
def decks_create(name: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), description: str = typer.Option(""), deck_type: str = typer.Option("freeform", "--type"), html_file: str = typer.Option(None, "--file"), personal: bool = typer.Option(False, "--personal"), as_json: bool = typer.Option(False, "--json")):
    """Create a deck. Use --file to load HTML from a file, or pipe via stdin."""
    html_content = ""
    if html_file:
        with open(html_file) as f:
            html_content = f.read()
    elif not sys.stdin.isatty():
        html_content = sys.stdin.read()
    with _client() as c:
        try:
            if personal:
                data = c.create_personal_deck(name, description=description, html_content=html_content, deck_type=deck_type)
            else:
                ws = workspace_id or _default_workspace()
                data = c.create_deck(ws, name, description=description, html_content=html_content, deck_type=deck_type)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Deck '{data['name']}' created.[/green]  ID: {data['id']}")


@decks_app.command("get")
def decks_get(deck_id: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), html_only: bool = typer.Option(False, "--html"), as_json: bool = typer.Option(False, "--json")):
    """Get a deck. --html to output only the HTML content."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.get_deck(ws, deck_id)
        except BoozleError as e:
            _err(e)
    if html_only:
        print(data.get("html_content", ""))
    elif _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[bold]{data['name']}[/bold]  ({data.get('deck_type', 'freeform')})")
        console.print(f"ID: {data['id']}")
        if data.get("description"):
            console.print(f"Description: {data['description']}")
        html = data.get("html_content", "")
        console.print(f"HTML: {len(html)} chars")


@decks_app.command("update")
def decks_update(deck_id: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), name: str = typer.Option(None, "--name"), description: str = typer.Option(None, "--description"), html_file: str = typer.Option(None, "--file"), as_json: bool = typer.Option(False, "--json")):
    """Update a deck. Use --file to load HTML, or pipe via stdin."""
    kwargs: dict = {}
    if name is not None:
        kwargs["name"] = name
    if description is not None:
        kwargs["description"] = description
    if html_file:
        with open(html_file) as f:
            kwargs["html_content"] = f.read()
    elif not sys.stdin.isatty():
        kwargs["html_content"] = sys.stdin.read()
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.update_deck(ws, deck_id, **kwargs)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Deck updated.[/green]")


@decks_app.command("share")
def decks_share(deck_id: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), name: str = typer.Option(None, "--name"), require_email: bool = typer.Option(False, "--require-email"), passcode: str = typer.Option(None, "--passcode"), as_json: bool = typer.Option(False, "--json")):
    """Create a public share link for a deck."""
    with _client() as c:
        try:
            ws = workspace_id
            kwargs: dict = {}
            if name:
                kwargs["name"] = name
            if require_email:
                kwargs["require_email"] = True
            if passcode:
                kwargs["passcode"] = passcode
            data = c.create_deck_share(deck_id, workspace_id=ws, **kwargs)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        cfg = load_config()
        base = cfg.get("public_url", cfg["base_url"])
        console.print(f"[green]Share link created:[/green] {base}/d/{data['token']}")


@decks_app.command("shares")
def decks_shares(deck_id: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")):
    """List share links for a deck."""
    with _client() as c:
        try:
            data = c.list_deck_shares(deck_id, workspace_id=workspace_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No share links.[/dim]")
        else:
            for s in data:
                status = "[green]active[/green]" if s.get("is_active") else "[red]inactive[/red]"
                views = s.get("view_count", 0)
                console.print(f"  /d/{s['token']}  {status}  views: {views}  (id: {str(s['id'])[:8]})")


@decks_app.command("analytics")
def decks_analytics(deck_id: str = typer.Argument(...), share_id: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")):
    """View analytics for a share link."""
    with _client() as c:
        try:
            data = c.get_share_analytics(deck_id, share_id, workspace_id=workspace_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"Views: {data.get('total_views', 0)}  Unique: {data.get('unique_viewers', 0)}  Avg duration: {data.get('avg_duration_seconds', 0)}s")
        viewers = data.get("viewers", [])
        if viewers:
            console.print("\n[bold]Viewers[/bold]")
            for v in viewers:
                who = v.get("viewer_email") or v.get("viewer_ip") or "anonymous"
                console.print(f"  {who}  duration: {v.get('total_duration_seconds', 0)}s  last: {str(v.get('last_active_at', ''))[:19]}")


# ===========================================================================
# Agents
# ===========================================================================

agents_app = typer.Typer(help="Manage agent identities.")
app.add_typer(agents_app, name="agents")


@agents_app.command("create")
def agents_create(name: str = typer.Argument(...), display_name: str = typer.Option(""), description: str = typer.Option(""), as_json: bool = typer.Option(False, "--json")):
    """Create agent identity."""
    with _client() as c:
        try:
            data = c.create_agent(name, display_name=display_name, description=description)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Agent '{data['name']}' created.[/green]  API key: [bold]{data['api_key']}[/bold]")


@agents_app.command("list")
def agents_list(all_: bool = typer.Option(False, "--all"), as_json: bool = typer.Option(False, "--json")):
    """List agents. --all includes workspace context."""
    with _client() as c:
        try:
            data = c.list_agents_with_context() if all_ else c.list_agents()
        except BoozleError as e:
            _err(e)
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
            _err(e)
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
            _err(e)
    console.print("[green]Deleted.[/green]")


# ===========================================================================
# Chat Watches
# ===========================================================================

watches_app = typer.Typer(help="Chat watch subscriptions for agent notifications.")
app.add_typer(watches_app, name="watches")


@watches_app.command("list")
def watches_list(as_json: bool = typer.Option(False, "--json")):
    """List watched chats."""
    with _client() as c:
        try:
            data = c.list_watches()
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No watched chats.[/dim]")
        else:
            for w in data:
                ws = f" [{w.get('workspace_name', '')}]" if w.get('workspace_name') else ""
                console.print(f"  {w['chat_name']}{ws}  chat_id={w['chat_id']}  last_read={str(w.get('last_read_at', ''))[:19]}")


@watches_app.command("add")
def watches_add(
    chat_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Watch a chat for new messages."""
    with _client() as c:
        try:
            data = c.watch_chat(chat_id, workspace_id=workspace_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Now watching chat {chat_id}.[/green]")


@watches_app.command("remove")
def watches_remove(chat_id: str = typer.Argument(...)):
    """Stop watching a chat."""
    with _client() as c:
        try:
            c.unwatch_chat(chat_id)
        except BoozleError as e:
            _err(e)
    console.print("[yellow]Unwatched.[/yellow]")


@app.command()
def unread(as_json: bool = typer.Option(False, "--json")):
    """Show unread messages across watched chats."""
    with _client() as c:
        try:
            data = c.get_unread()
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        items = data.get("unread", [])
        if not items or data.get("total_unread", 0) == 0:
            console.print("[dim]No unread messages.[/dim]")
        else:
            for item in items:
                if item["unread_count"] == 0:
                    continue
                ws = f" [{item.get('workspace_name', '')}]" if item.get('workspace_name') else ""
                console.print(f"  #{item['chat_name']}{ws}: [bold]{item['unread_count']}[/bold] unread")


@app.command("mark-read")
def mark_read_cmd(chat_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Mark a watched chat as read."""
    with _client() as c:
        try:
            data = c.mark_read(chat_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Marked as read.[/green]")


# ===========================================================================
# Poll + Notify
# ===========================================================================

@app.command()
def poll(workspace_id: str = typer.Option(None, "--ws"), chat_id: str = typer.Option(None, "--chat"), room_id: str = typer.Option(None, "--room"), interval: int = typer.Option(5, "-i")):
    """Poll for new messages (JSON lines to stdout). Use --room for personal rooms."""
    ws = workspace_id or (None if room_id else _default_workspace())
    ch = chat_id or (None if room_id else _default_chat())
    last_ts = None
    with _client() as c:
        try:
            if room_id:
                msgs = c.read_room_messages(room_id, limit=1)
            else:
                msgs = c.read_messages(ws, ch, limit=1)
            if msgs:
                last_ts = msgs[-1].get("created_at")
        except BoozleError:
            pass
        console.print("[dim]Polling... (Ctrl+C to stop)[/dim]", stderr=True)
        try:
            while True:
                time.sleep(interval)
                try:
                    if room_id:
                        msgs = c.read_room_messages(room_id, limit=50, after=last_ts)
                    else:
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
    add_notify_room(room_id)
    console.print("[green]Subscribed.[/green]")


@notify_app.command("off")
def notify_off(room_id: str = typer.Argument(...)):
    remove_notify_room(room_id)
    console.print("[yellow]Unsubscribed.[/yellow]")


@notify_app.command("list")
def notify_list():
    rooms = get_notify_rooms()
    if not rooms:
        console.print("[dim]None.[/dim]")
    else:
        for r in rooms:
            console.print(f"  - {r}")


# ===========================================================================
# Config
# ===========================================================================

@app.command("config")
def config_cmd(key: Optional[str] = typer.Argument(None), value: Optional[str] = typer.Argument(None)):
    """Show or set config. Keys: base_url, default_workspace, default_chat, default_store, output_format."""
    if key and value:
        cfg = load_config()
        cfg[key] = value
        save_config(**{k: v for k, v in cfg.items() if k in [
            "base_url", "api_key", "username", "default_workspace", "default_chat",
            "default_store", "output_format", "public_url",
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
