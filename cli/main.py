"""Boozle CLI — command-line interface for workspaces, chats, notebooks, tables, history, and decks."""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

import typer

from .client import BoozleClient, BoozleError
from .config import load_config, save_config, add_notify_room, get_notify_rooms, remove_notify_room
from .formatting import console, output_json, print_personas, print_members, print_messages, print_rooms, print_user

app = typer.Typer(name="boozle", help="Boozle CLI — workspaces, chats, notebooks, tables, history, decks.")


def _client() -> BoozleClient:
    cfg = load_config()
    return BoozleClient(base_url=cfg["base_url"], api_key=cfg.get("api_key", ""))


def _use_json(flag: bool) -> bool:
    return flag or load_config().get("output_format") == "json"


def _default_workspace() -> str:
    ws = load_config().get("default_workspace", "")
    if not ws:
        console.print("[red]No default workspace. Run [bold]boozle setup[/bold] or set manually: boozle config default_workspace <id>[/red]")
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
def register(
    name: str = typer.Argument(...),
    type: str = typer.Option("human"),
    description: str = typer.Option(""),
    password: str = typer.Option(None, "--password", help="Password (required for human accounts)"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create account and store API key."""
    if type == "human" and not password:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    with _client() as c:
        try:
            data = c.register(name, user_type=type, description=description, password=password)
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
def read(workspace_id: str = typer.Option(None, "--ws"), chat_id: str = typer.Option(None, "--chat"), room_id: str = typer.Option(None, "--room"), dm_id: str = typer.Option(None, "--dm"), limit: int = typer.Option(50, "-n", "--limit"), after: Optional[str] = typer.Option(None, "--after"), as_json: bool = typer.Option(False, "--json")):
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
def hist_query(workspace_id: str = typer.Option(None, "--ws"), store_id: str = typer.Option(None, "--store"), agent_name: str = typer.Option(None, "--agent"), event_type: str = typer.Option(None, "--type"), limit: int = typer.Option(50, "-n", "--limit"), all_: bool = typer.Option(False, "--all"), as_json: bool = typer.Option(False, "--json")):
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
def hist_search(query: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), store_id: str = typer.Option(None, "--store"), limit: int = typer.Option(50, "-n", "--limit"), as_json: bool = typer.Option(False, "--json")):
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


@hist_app.command("ask")
def hist_ask(question: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), store_id: str = typer.Option(None, "--store"), as_json: bool = typer.Option(False, "--json")):
    """Ask a question about a history store (LLM-powered)."""
    ws = workspace_id or _default_workspace()
    store = store_id or load_config().get("default_store", "")
    if not store:
        console.print("[red]No store specified.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        try:
            data = c.query_history(ws, store, question)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"\n[bold]{data.get('answer', '')}[/bold]\n")
        sources = data.get("sources", [])
        if sources:
            console.print(f"[dim]Based on {len(sources)} events[/dim]")


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
# Tables
# ===========================================================================

tables_app = typer.Typer(help="Tables — structured data with typed columns and rows.")
app.add_typer(tables_app, name="tables")


def _resolve_col_names(table: dict, data: dict) -> dict:
    """Translate column names to IDs in a data dict."""
    cols = table.get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    id_set = {col["id"] for col in cols}
    resolved = {}
    for k, v in data.items():
        if k in id_set:
            resolved[k] = v
        elif k in name_to_id:
            resolved[name_to_id[k]] = v
    return resolved


def _resolve_filter_names(table: dict, filters_json: str) -> str:
    """Resolve column names in filter JSON to column IDs."""
    if not filters_json:
        return filters_json
    cols = table.get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    parsed = json.loads(filters_json)
    for f in parsed:
        cid = f.get("column_id", "")
        if cid in name_to_id:
            f["column_id"] = name_to_id[cid]
    return json.dumps(parsed)


def _resolve_sort_name(table: dict, sort_by: str) -> str:
    """Resolve column name to ID for sorting."""
    if not sort_by:
        return sort_by
    cols = table.get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    return name_to_id.get(sort_by, sort_by)


@tables_app.command("list")
def tables_list(workspace_id: str = typer.Option(None, "--ws"), all_: bool = typer.Option(False, "--all"), personal: bool = typer.Option(False, "--personal"), as_json: bool = typer.Option(False, "--json")):
    """List tables. --all for cross-workspace, --personal for personal tables."""
    with _client() as c:
        try:
            if all_:
                data = c.all_tables()
            elif personal:
                data = c.list_personal_tables()
            else:
                data = c.list_tables(workspace_id or _default_workspace())
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No tables.[/dim]")
        else:
            for t in data:
                ws = f" [{t.get('workspace_name', '')}]" if t.get("workspace_name") else ""
                cols = len(t.get("columns", []))
                rows = t.get("row_count", 0)
                console.print(f"  {t['name']}{ws}  ({cols} cols, {rows} rows, id: {str(t['id'])[:8]})")


@tables_app.command("create")
def tables_create(
    name: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    description: str = typer.Option(""),
    columns: str = typer.Option(None, "--columns", help='JSON: [{"name":"Col","type":"text"}]'),
    personal: bool = typer.Option(False, "--personal"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a table. --columns accepts JSON array of {name, type, options?}."""
    cols = json.loads(columns) if columns else []
    with _client() as c:
        try:
            if personal:
                data = c.create_personal_table(name, description=description, columns=cols)
            else:
                ws = workspace_id or _default_workspace()
                data = c.create_table(ws, name, description=description, columns=cols)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Table '{data['name']}' created.[/green]  ID: {data['id']}")


@tables_app.command("update")
def tables_update(
    table_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    name: str = typer.Option(None, "--name"),
    description: str = typer.Option(None, "--description"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Update a table's name or description."""
    kwargs: dict = {}
    if name is not None:
        kwargs["name"] = name
    if description is not None:
        kwargs["description"] = description
    if not kwargs:
        console.print("[red]Provide --name or --description to update.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.update_table(ws, table_id, **kwargs)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Table updated.[/green]")


@tables_app.command("schema")
def tables_schema(table_id: str = typer.Argument(...), workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")):
    """Show a table's column schema."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.get_table(ws, table_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[bold]{data['name']}[/bold]  ({data.get('row_count', 0)} rows)")
        cols = data.get("columns", [])
        if not cols:
            console.print("[dim]No columns defined.[/dim]")
        else:
            for col in sorted(cols, key=lambda c: c.get("order", 0)):
                extra = ""
                if col.get("options"):
                    extra = f"  options: {', '.join(col['options'])}"
                if col.get("required"):
                    extra += "  REQUIRED"
                console.print(f"  {col['name']}  [dim]({col['type']}, {col['id']})[/dim]{extra}")


@tables_app.command("rows")
def tables_rows(
    table_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    limit: int = typer.Option(50, "-n", "--limit"),
    offset: int = typer.Option(0, "--offset"),
    sort_by: str = typer.Option("", "--sort", help="Column name or ID to sort by"),
    sort_order: str = typer.Option("asc", "--order"),
    filters: str = typer.Option("", "--filter", help='JSON: [{"column_id":"Name","op":"eq","value":"Alice"}]'),
    as_json: bool = typer.Option(False, "--json"),
):
    """Read rows. --sort and --filter accept column names (auto-resolved)."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            table = c.get_table(ws, table_id)
            id_to_name = {col["id"]: col["name"] for col in table.get("columns", [])}
            resolved_sort = _resolve_sort_name(table, sort_by)
            resolved_filters = _resolve_filter_names(table, filters) if filters else ""
            result = c.list_table_rows(ws, table_id, limit=limit, offset=offset, sort_by=resolved_sort, sort_order=sort_order, filters=resolved_filters)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        rows = result.get("rows", []) if isinstance(result, dict) else result
        total = result.get("total_count", len(rows)) if isinstance(result, dict) else len(rows)
        console.print(f"[dim]Showing {len(rows)} of {total} rows[/dim]")
        for row in rows:
            named = {id_to_name.get(k, k): v for k, v in row.get("data", {}).items()}
            console.print(f"  [{str(row['id'])[:8]}] {named}")


@tables_app.command("insert")
def tables_insert(
    table_id: str = typer.Argument(...),
    data: str = typer.Argument(..., help='JSON: {"Name":"Alice","Status":"active"}'),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Insert a row. Data is a JSON object with column names as keys."""
    row_data = json.loads(data)
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            table = c.get_table(ws, table_id)
            resolved = _resolve_col_names(table, row_data)
            result = c.insert_table_row(ws, table_id, resolved)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print(f"[green]Row inserted.[/green]  ID: {result['id']}")


@tables_app.command("import")
def tables_import(
    table_id: str = typer.Argument(...),
    file: str = typer.Option(None, "--file", "-f", help="CSV or JSON file path (or pipe via stdin)"),
    format_: str = typer.Option("auto", "--format", help="csv, json, or auto (detect from extension/content)"),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Bulk import rows from CSV or JSON. Auto-chunks into batches of 5000.
    CSV: first row is column headers. JSON: array of objects.
    Pipe: cat data.csv | boozle tables import <table_id> --format csv"""
    import csv as csv_mod
    import io as io_mod

    # Read input
    if file:
        with open(file) as f:
            raw = f.read()
        if format_ == "auto":
            format_ = "csv" if file.endswith(".csv") else "json"
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
        if format_ == "auto":
            raw_stripped = raw.strip()
            format_ = "json" if raw_stripped.startswith("[") or raw_stripped.startswith("{") else "csv"
    else:
        console.print("[red]Provide --file or pipe data via stdin.[/red]")
        raise typer.Exit(1)

    # Parse rows
    rows_data: list[dict] = []
    if format_ == "csv":
        reader = csv_mod.DictReader(io_mod.StringIO(raw))
        for row in reader:
            rows_data.append(dict(row))
    else:
        parsed = json.loads(raw)
        rows_data = parsed if isinstance(parsed, list) else [parsed]

    if not rows_data:
        console.print("[dim]No rows to import.[/dim]")
        return

    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            table = c.get_table(ws, table_id)

            # Resolve column names to IDs
            resolved_rows = [_resolve_col_names(table, r) for r in rows_data]

            # Chunk into batches of 5000
            batch_size = 5000
            total_inserted = 0
            for i in range(0, len(resolved_rows), batch_size):
                batch = resolved_rows[i:i + batch_size]
                c.insert_table_rows_batch(ws, table_id, batch)
                total_inserted += len(batch)
                if len(resolved_rows) > batch_size:
                    console.print(f"  [dim]Inserted {total_inserted}/{len(resolved_rows)} rows...[/dim]")
        except BoozleError as e:
            _err(e)

    if _use_json(as_json):
        output_json({"imported": total_inserted})
    else:
        console.print(f"[green]Imported {total_inserted} rows.[/green]")


@tables_app.command("update-row")
def tables_update_row(
    table_id: str = typer.Argument(...),
    row_id: str = typer.Argument(...),
    data: str = typer.Argument(..., help='JSON: {"Status":"done"}'),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Update a row (partial merge). Data is JSON with column names as keys."""
    row_data = json.loads(data)
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            table = c.get_table(ws, table_id)
            resolved = _resolve_col_names(table, row_data)
            result = c.update_table_row(ws, table_id, row_id, resolved)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print("[green]Row updated.[/green]")


@tables_app.command("delete-row")
def tables_delete_row(
    table_id: str = typer.Argument(...),
    row_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Delete a row from a table."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            c.delete_table_row(ws, table_id, row_id)
        except BoozleError as e:
            _err(e)
    console.print("[green]Row deleted.[/green]")


@tables_app.command("add-column")
def tables_add_column(
    table_id: str = typer.Argument(...),
    name: str = typer.Argument(...),
    col_type: str = typer.Option("text", "--type"),
    options: str = typer.Option("", "--options", help="Comma-separated options for select/multiselect"),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Add a column to a table."""
    opts = [o.strip() for o in options.split(",") if o.strip()] if options else None
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            result = c.add_table_column(ws, table_id, name, col_type=col_type, options=opts)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print(f"[green]Column '{name}' ({col_type}) added.[/green]")


@tables_app.command("delete-column")
def tables_delete_column(
    table_id: str = typer.Argument(...),
    column_id: str = typer.Argument(..., help="Column ID (col_xxx) or column name"),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Delete a column from a table."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            # Resolve column name to ID if needed
            if not column_id.startswith("col_"):
                table = c.get_table(ws, table_id)
                name_to_id = {col["name"]: col["id"] for col in table.get("columns", [])}
                if column_id in name_to_id:
                    column_id = name_to_id[column_id]
            result = c.delete_table_column(ws, table_id, column_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print(f"[green]Column deleted.[/green]")


@tables_app.command("count")
def tables_count(
    table_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    filters: str = typer.Option("", "--filter", help="JSON filter array"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Count rows, optionally with filters."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            if filters:
                table = c.get_table(ws, table_id)
                filters = _resolve_filter_names(table, filters)
            params: dict = {}
            if filters:
                params["filters"] = filters
            result = c._get(f"/api/v1/workspaces/{ws}/tables/{table_id}/rows/count", **params)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print(f"Count: {result.get('count', 0)}")


@tables_app.command("export")
def tables_export(
    table_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    file: str = typer.Option(None, "--file", "-f", help="Output file (default: stdout)"),
    filters: str = typer.Option("", "--filter"),
    sort_by: str = typer.Option("", "--sort"),
    sort_order: str = typer.Option("asc", "--order"),
):
    """Export table as CSV."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            params: dict = {"sort_order": sort_order}
            if sort_by:
                table = c.get_table(ws, table_id)
                params["sort_by"] = _resolve_sort_name(table, sort_by)
            if filters:
                if "table" not in dir():
                    table = c.get_table(ws, table_id)
                params["filters"] = _resolve_filter_names(table, filters)
            resp = c._request("GET", f"/api/v1/workspaces/{ws}/tables/{table_id}/export/csv", params=params)
            csv_content = resp.text
        except BoozleError as e:
            _err(e)
    if file:
        with open(file, "w") as f:
            f.write(csv_content)
        console.print(f"[green]Exported to {file}[/green]")
    else:
        print(csv_content, end="")


@tables_app.command("delete")
def tables_delete(
    table_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """Delete a table and all its data."""
    if not yes:
        typer.confirm("Delete this table and all its data?", abort=True)
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            c.delete_table(ws, table_id)
        except BoozleError as e:
            _err(e)
    console.print("[green]Table deleted.[/green]")


# ===========================================================================
# Personas
# ===========================================================================

personas_app = typer.Typer(help="Manage persona identities.")
app.add_typer(personas_app, name="personas")


@personas_app.command("create")
def personas_create(name: str = typer.Argument(...), display_name: str = typer.Option(""), description: str = typer.Option(""), as_json: bool = typer.Option(False, "--json")):
    """Create persona identity."""
    with _client() as c:
        try:
            data = c.create_persona(name, display_name=display_name, description=description)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Persona '{data['name']}' created.[/green]  API key: [bold]{data['api_key']}[/bold]")


@personas_app.command("list")
def personas_list(all_: bool = typer.Option(False, "--all"), as_json: bool = typer.Option(False, "--json")):
    """List personas. --all includes workspace context."""
    with _client() as c:
        try:
            data = c.list_personas_with_context() if all_ else c.list_personas()
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_personas(data)


@personas_app.command("rotate-key")
def personas_rotate_key(persona_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Rotate persona API key."""
    with _client() as c:
        try:
            data = c.rotate_persona_key(persona_id)
        except BoozleError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]New key: [bold]{data['api_key']}[/bold][/green]")


@personas_app.command("delete")
def personas_delete(persona_id: str = typer.Argument(...), confirm: bool = typer.Option(False, "--yes", "-y")):
    """Delete persona."""
    if not confirm:
        typer.confirm(f"Delete persona {persona_id}?", abort=True)
    with _client() as c:
        try:
            c.delete_persona(persona_id)
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
# Setup wizard
# ===========================================================================

@app.command("setup")
def setup():
    """Interactive first-time setup. Sets base URL, authenticates, and configures defaults."""
    console.print("\n[bold]Boozle setup[/bold]  (press Enter to accept defaults)\n")

    # --- Step 1: API endpoint ---
    cfg = load_config()
    current_url = cfg.get("base_url", "http://localhost:3456")
    default_url = "https://getboozle.com" if "localhost" in current_url else current_url
    base_url = typer.prompt("API endpoint", default=default_url).rstrip("/")
    save_config(base_url=base_url)

    # --- Step 2: Auth ---
    has_key = bool(cfg.get("api_key"))
    if has_key:
        try:
            with BoozleClient(base_url=base_url, api_key=cfg["api_key"]) as c:
                user = c.whoami()
            console.print(f"  [green]✓[/green] Already authenticated as [bold]{user['name']}[/bold]")
        except BoozleError:
            has_key = False

    if not has_key:
        action = typer.prompt("Login or register? [login/register]", default="login").strip().lower()
        name = typer.prompt("Username")
        if action == "register":
            password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
            with BoozleClient(base_url=base_url, api_key="") as c:
                try:
                    data = c.register(name, user_type="human", description="", password=password)
                except BoozleError as e:
                    console.print(f"[red]Registration failed: {e.detail}[/red]")
                    raise typer.Exit(1)
            save_config(api_key=data["api_key"], username=data["name"])
            console.print(f"  [green]✓[/green] Registered as [bold]{data['name']}[/bold]")
        else:
            password = typer.prompt("Password", hide_input=True)
            with BoozleClient(base_url=base_url, api_key="") as c:
                try:
                    data = c.login(name, password)
                except BoozleError as e:
                    console.print(f"[red]Login failed: {e.detail}[/red]")
                    raise typer.Exit(1)
            save_config(api_key=data["api_key"], username=data["name"])
            console.print(f"  [green]✓[/green] Logged in as [bold]{data['name']}[/bold]")

    # Reload config after auth
    cfg = load_config()

    with BoozleClient(base_url=base_url, api_key=cfg["api_key"]) as c:
        # --- Step 3: Workspace ---
        try:
            my_workspaces = c.list_workspaces(mine=True)
        except BoozleError:
            my_workspaces = []

        workspace_id = cfg.get("default_workspace", "")
        if my_workspaces:
            console.print(f"\n  Your workspaces:")
            for ws in my_workspaces[:5]:
                marker = " [dim](current default)[/dim]" if str(ws["id"]) == workspace_id else ""
                console.print(f"    [dim]{str(ws['id'])[:8]}…[/dim]  {ws['name']}{marker}")

        ws_action = typer.prompt(
            "\nUse existing workspace ID, or type a name to create new one",
            default=workspace_id or "",
        ).strip()

        if not ws_action:
            console.print("[yellow]Skipping workspace setup. Run: boozle config default_workspace <id>[/yellow]")
        else:
            # Check if it looks like a UUID (existing) or a name (create new)
            import re
            is_uuid = bool(re.match(r"^[0-9a-f-]{32,36}$", ws_action, re.I))
            if is_uuid:
                workspace_id = ws_action
                save_config(default_workspace=workspace_id)
                console.print(f"  [green]✓[/green] Default workspace set to [bold]{workspace_id[:8]}…[/bold]")
            else:
                try:
                    ws_data = c.create_workspace(ws_action)
                    workspace_id = str(ws_data["id"])
                    save_config(default_workspace=workspace_id)
                    console.print(f"  [green]✓[/green] Created workspace [bold]{ws_data['name']}[/bold]  invite: {ws_data['invite_code']}")
                except BoozleError as e:
                    console.print(f"[red]Could not create workspace: {e.detail}[/red]")

        # --- Step 4: History store ---
        if workspace_id:
            try:
                stores = c.list_histories(workspace_id)
            except BoozleError:
                stores = []

            store_id = cfg.get("default_store", "")
            if stores:
                console.print(f"\n  Existing history stores:")
                for s in stores[:5]:
                    marker = " [dim](current default)[/dim]" if str(s["id"]) == store_id else ""
                    console.print(f"    [dim]{str(s['id'])[:8]}…[/dim]  {s['name']}{marker}")

            store_action = typer.prompt(
                "\nUse existing store ID, or type a name to create new one",
                default=store_id or "main",
            ).strip()

            is_uuid = bool(re.match(r"^[0-9a-f-]{32,36}$", store_action, re.I))
            if is_uuid:
                save_config(default_store=store_action)
                console.print(f"  [green]✓[/green] Default store set to [bold]{store_action[:8]}…[/bold]")
            else:
                try:
                    store_data = c.create_history(workspace_id, store_action)
                    save_config(default_store=str(store_data["id"]))
                    console.print(f"  [green]✓[/green] Created history store [bold]{store_data['name']}[/bold]")
                except BoozleError as e:
                    console.print(f"[red]Could not create history store: {e.detail}[/red]")

    # --- Done ---
    console.print("\n[bold green]Setup complete.[/bold green]")
    console.print("  Run [bold]boozle whoami[/bold] to confirm auth.")
    console.print("  Run [bold]boozle history push \"hello\"[/bold] to push your first event.")
    console.print("  Run [bold]boozle --help[/bold] to see all commands.\n")


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


# ===========================================================================
# Import Bookmarks
# ===========================================================================


@app.command("import-bookmarks")
def import_bookmarks_cmd(
    file: str = typer.Argument(..., help="Path to bookmarks .html file (Chrome/Firefox export)"),
    notebook: str = typer.Option("Bookmarks", "--notebook", "-n", help="Notebook name to create or use"),
    workspace_id: str = typer.Option(None, "--ws", help="Workspace ID (uses personal notebook if omitted)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be imported without importing"),
    skip_scrape: bool = typer.Option(False, "--skip-scrape", help="Import titles + URLs only, skip content extraction"),
    delay: float = typer.Option(0.5, "--delay", help="Seconds between scrape requests"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Import bookmarks from a Chrome/Firefox HTML export.

    Parses the bookmark file, scrapes each URL (web articles, YouTube transcripts,
    PDFs), and stores them as notebook pages. The sleep agent will curate them into
    a searchable wiki.

    Export bookmarks: Chrome → Bookmarks → ⋮ → Export bookmarks
    """
    from pathlib import Path
    from .bookmark_parser import parse_bookmark_file, unique_folders
    from .scraper import scrape_bookmarks, format_page_content

    path = Path(file)
    if not path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    # Parse
    bookmarks = parse_bookmark_file(path)
    folders = unique_folders(bookmarks)
    console.print(f"[green]Found {len(bookmarks)} bookmarks in {len(folders)} folders[/green]")

    if not bookmarks:
        console.print("[yellow]No bookmarks found in the file.[/yellow]")
        raise typer.Exit(0)

    # Dry run
    if dry_run:
        from rich.table import Table
        table = Table(title="Bookmarks to import")
        table.add_column("Folder", style="dim")
        table.add_column("Title")
        table.add_column("URL", style="dim")
        for b in bookmarks[:100]:
            table.add_row(b.folder_label, b.title[:50], b.url[:60])
        if len(bookmarks) > 100:
            table.add_row("...", f"({len(bookmarks) - 100} more)", "")
        console.print(table)
        raise typer.Exit(0)

    # Scrape content (unless skip_scrape)
    scraped: dict[str, tuple[str | None, str]] = {}
    if not skip_scrape:
        scraped = scrape_bookmarks(bookmarks, delay=delay)

    # Create or reuse notebook
    with _client() as c:
        try:
            if workspace_id:
                nb = c.create_notebook(workspace_id, notebook)
            else:
                nb = c.create_personal_notebook(notebook)
        except BoozleError as e:
            if e.status_code == 409:
                # Notebook exists, find it
                if workspace_id:
                    nbs = c.list_notebooks(workspace_id)
                else:
                    nbs = c.list_personal_notebooks()
                nb = next((n for n in nbs if n["name"] == notebook), None)
                if not nb:
                    console.print(f"[red]Notebook '{notebook}' exists but could not be found[/red]")
                    raise typer.Exit(1)
            else:
                _err(e)

        notebook_id = nb["id"]
        console.print(f"Notebook: [bold]{nb['name']}[/bold] ({notebook_id})")

        # Create folders
        folder_ids: dict[str, str] = {}
        for folder_name in folders:
            try:
                if workspace_id:
                    f = c.create_folder(workspace_id, notebook_id, folder_name)
                else:
                    f = c.create_personal_folder(notebook_id, folder_name)
                folder_ids[folder_name] = f["id"]
            except BoozleError:
                pass  # Folder may already exist, skip

        # Import bookmarks as pages
        imported = 0
        failed = 0
        skipped_scrape_count = 0

        from rich.progress import Progress as RichProgress
        with RichProgress(transient=False) as progress:
            task = progress.add_task("Importing pages...", total=len(bookmarks))

            for bm in bookmarks:
                progress.advance(task)
                content_md = None
                content_type = "unknown"

                if bm.url in scraped:
                    content_md, content_type = scraped[bm.url]
                    if not content_md:
                        skipped_scrape_count += 1

                page_content = format_page_content(bm, content_md, content_type)
                folder_id = folder_ids.get(bm.folder_label)

                # Truncate title to avoid API errors
                page_name = bm.title[:200] if bm.title else bm.url[:200]

                try:
                    if workspace_id:
                        c.create_page(workspace_id, notebook_id, page_name, page_content, folder_id=folder_id)
                    else:
                        c.create_personal_page(notebook_id, page_name, page_content)
                    imported += 1
                except BoozleError:
                    failed += 1

    # Summary
    console.print(f"\n[green]Imported {imported} bookmarks[/green]")
    if failed:
        console.print(f"[yellow]Failed: {failed}[/yellow]")
    if skipped_scrape_count:
        console.print(f"[dim]Scrape failed for {skipped_scrape_count} URLs (stored as links only)[/dim]")
    if not skip_scrape:
        yt = sum(1 for _, (_, t) in scraped.items() if t == "youtube" and _ is not None)
        pdf = sum(1 for _, (_, t) in scraped.items() if t == "pdf" and _ is not None)
        art = sum(1 for _, (c, t) in scraped.items() if t == "article" and c is not None)
        if yt or pdf or art:
            console.print(f"[dim]Content extracted: {art} articles, {yt} YouTube transcripts, {pdf} PDFs[/dim]")


# ===========================================================================
# Universal Search
# ===========================================================================


@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Question or search query"),
    workspace_id: str = typer.Option(None, "--ws", help="Workspace ID (searches personal resources if omitted)"),
    types: str = typer.Option(None, "--types", help="Comma-separated resource types: history,notebook,table,document"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Search across all your knowledge — notebooks, history, tables, documents.

    Uses AI-powered synthesis to find answers across all your ingested data.
    """
    resource_types = [t.strip() for t in types.split(",")] if types else None

    with _client() as c:
        try:
            if workspace_id:
                result = c.universal_search(workspace_id, query, resource_types=resource_types)
            else:
                result = c.personal_search(query, resource_types=resource_types)
        except BoozleError as e:
            _err(e)

    if _use_json(as_json):
        output_json(result)
    else:
        answer = result.get("answer", "No answer found.")
        sources = result.get("sources_used", [])
        console.print(f"\n{answer}\n")
        if sources:
            console.print(f"[dim]Sources: {', '.join(sources)}[/dim]")


if __name__ == "__main__":
    app()
