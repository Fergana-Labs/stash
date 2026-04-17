"""Stash CLI — command-line interface for workspaces, notebooks, tables, history, and search."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import questionary
import typer
from rich.panel import Panel

from .client import StashClient, StashError
from .config import (
    PROJECT_FILENAME,
    Manifest,
    find_project_config,
    find_project_manifest,
    load_config,
    load_manifest,
    save_config,
)
from .formatting import console, output_json, print_members, print_rooms, print_user

app = typer.Typer(name="stash", help="Stash CLI — workspaces, notebooks, tables, history.")


def _client() -> StashClient:
    cfg = load_config()
    return StashClient(base_url=cfg["base_url"], api_key=cfg.get("api_key", ""))


def _use_json(flag: bool) -> bool:
    return flag or load_config().get("output_format") == "json"


def _default_workspace() -> str:
    ws = load_config().get("default_workspace", "")
    if not ws:
        console.print(
            "[red]No default workspace. Run [bold]stash connect[/bold] or set manually: stash config default_workspace <id>[/red]"
        )
        raise typer.Exit(1)
    return ws


def _err(e: StashError) -> None:
    console.print(f"[red]Error [{e.status_code}]: {e.detail}[/red]")
    raise typer.Exit(1)


# ===========================================================================
# Auth
# ===========================================================================


@app.command()
def register(
    name: str = typer.Argument(...),
    password: str = typer.Option(None, "--password", help="Password for the account"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create account and store API key."""
    if not password:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    with _client() as c:
        try:
            data = c.register(name, description="", password=password)
        except StashError as e:
            _err(e)
    save_config(api_key=data["api_key"], username=data["name"])
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(
            f"[green]Registered as {data['name']}[/green]  API key: [bold]{data['api_key']}[/bold]"
        )


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
        except StashError as e:
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
    with StashClient(base_url=base_url, api_key=api_key) as c:
        try:
            user = c.whoami()
            save_config(username=user["name"])
            console.print(f"[green]Authenticated as {user['name']}[/green]")
        except StashError:
            console.print("[yellow]Saved but could not verify.[/yellow]")


@app.command()
def whoami(as_json: bool = typer.Option(False, "--json")):
    """Show profile."""
    with _client() as c:
        try:
            data = c.whoami()
        except StashError as e:
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
def ws_list(
    mine: bool = typer.Option(False, "--mine"), as_json: bool = typer.Option(False, "--json")
):
    """List workspaces."""
    with _client() as c:
        try:
            data = c.list_workspaces(mine=mine)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_rooms(data, title="My Workspaces" if mine else "Public Workspaces")


@ws_app.command("create")
def ws_create(
    name: str = typer.Argument(...),
    description: str = typer.Option(""),
    public: bool = typer.Option(False, "--public"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create workspace."""
    with _client() as c:
        try:
            data = c.create_workspace(name, description=description, is_public=public)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(
            f"[green]Created '{data['name']}'[/green]  ID: {data['id']}  Invite: {data['invite_code']}"
        )


@ws_app.command("join")
def ws_join(invite_code: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Join workspace by invite code."""
    with _client() as c:
        try:
            data = c.join_workspace(invite_code)
        except StashError as e:
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
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(
            f"[bold]{data['name']}[/bold]  Members: {data.get('member_count', '?')}  Public: {data['is_public']}"
        )
        console.print(f"ID: {data['id']}  Invite: {data['invite_code']}")


@ws_app.command("members")
def ws_members(
    workspace_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")
):
    """List workspace members."""
    with _client() as c:
        try:
            data = c.workspace_members(workspace_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_members(data)


# ===========================================================================
# Magic-link invites
# ===========================================================================

invite_app = typer.Typer(
    help="Magic-link invites — single-use, TTL-bounded tokens for zero-friction workspace onboarding.",
    invoke_without_command=True,
)
app.add_typer(invite_app, name="invite")


def _format_invite_share_block(
    token: str, base_url: str, workspace_name: str, max_uses: int, expires_at: str
) -> str:
    """The prose the sender copies into Slack/DMs to share a workspace."""
    return (
        "\n"
        f"  pipx install stashai && \\\n"
        f"    stash connect --invite {token} --endpoint {base_url.rstrip('/')}\n"
        "\n"
    )


@invite_app.callback()
def invite_default(
    ctx: typer.Context,
    workspace_id: str = typer.Option(None, "--ws"),
    uses: int = typer.Option(1, "--uses", help="Maximum times the link can be redeemed."),
    days: int = typer.Option(7, "--days", help="Days until the link expires."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Mint a shareable invite link for a workspace (default: your default workspace)."""
    if ctx.invoked_subcommand is not None:
        return
    ws = workspace_id or _default_workspace()
    cfg = load_config()
    with _client() as c:
        try:
            data = c.create_invite_token(ws, max_uses=uses, ttl_days=days)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    share_block = _format_invite_share_block(
        token=data["token"],
        base_url=cfg.get("base_url", ""),
        workspace_name=data["workspace_name"],
        max_uses=data["max_uses"],
        expires_at=str(data["expires_at"])[:10],
    )
    console.print(
        f"\n[green]Generated invite for [bold]{data['workspace_name']}[/bold][/green]"
        f"  [dim](id: {data['id']})[/dim]\n"
    )
    console.print(
        Panel(
            share_block,
            title="[bold]Have your teammate paste this into claude code[/bold]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print(
        "\n[dim]Revoke anytime with:[/dim] " f"[cyan]stash invite revoke {data['id']}[/cyan]\n"
    )


@invite_app.command("list")
def invite_list(
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List active invite tokens for a workspace."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            tokens = c.list_invite_tokens(ws)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(tokens)
        return
    if not tokens:
        console.print("[dim]No invite tokens.[/dim]")
        return
    console.print(f"[bold]Invite tokens for workspace {ws[:8]}…[/bold]\n")
    for t in tokens:
        status = "revoked" if t.get("revoked_at") else f"{t['uses_count']}/{t['max_uses']} used"
        console.print(
            f"  [dim]{str(t['id'])[:8]}…[/dim]  {status}  " f"expires {str(t['expires_at'])[:10]}"
        )


@invite_app.command("revoke")
def invite_revoke(
    token_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Revoke an invite token so it can no longer be redeemed."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            c.revoke_invite_token(ws, token_id)
        except StashError as e:
            _err(e)
    console.print(f"[green]Revoked invite token {token_id[:8]}…[/green]")


# ===========================================================================
# Notebooks
# ===========================================================================

nb_app = typer.Typer(help="Notebook collections (folders + markdown pages).")
app.add_typer(nb_app, name="notebooks")


@nb_app.command("list")
def nb_list(
    workspace_id: str = typer.Option(None, "--ws"),
    all_: bool = typer.Option(False, "--all"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List notebooks. --all for cross-workspace, --ws for single workspace."""
    with _client() as c:
        try:
            data = (
                c.all_notebooks()
                if all_
                else c.list_notebooks(workspace_id or _default_workspace())
            )
        except StashError as e:
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
def nb_create(
    name: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    description: str = typer.Option(""),
    personal: bool = typer.Option(False, "--personal"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a notebook collection."""
    with _client() as c:
        try:
            if personal:
                data = c.create_personal_notebook(name, description=description)
            else:
                ws = workspace_id or _default_workspace()
                data = c.create_notebook(ws, name, description=description)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Notebook '{data['name']}' created.[/green]  ID: {data['id']}")


@nb_app.command("pages")
def nb_pages(
    notebook_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List pages in a notebook."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.list_page_tree(ws, notebook_id)
        except StashError as e:
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
def nb_add_page(
    notebook_id: str = typer.Argument(...),
    name: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    content: str = typer.Option(""),
    as_json: bool = typer.Option(False, "--json"),
):
    """Add a page to a notebook."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.create_page(ws, notebook_id, name, content=content)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Page '{data['name']}' created.[/green]  ID: {data['id']}")


@nb_app.command("read-page")
def nb_read_page(
    notebook_id: str = typer.Argument(...),
    page_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Read a page's content."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.get_page(ws, notebook_id, page_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[bold]{data['name']}[/bold]\n")
        console.print(data.get("content_markdown", ""))


@nb_app.command("edit-page")
def nb_edit_page(
    notebook_id: str = typer.Argument(...),
    page_id: str = typer.Argument(...),
    content: str = typer.Option(None, "--content"),
    name: str = typer.Option(None, "--name"),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
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
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Page updated.[/green]")


# ===========================================================================
# History (was memory stores)
# ===========================================================================

hist_app = typer.Typer(help="History — structured agent event logs.")
app.add_typer(hist_app, name="history")


@hist_app.command("agents")
def hist_agents(
    workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")
):
    """List distinct agent names that have logged events in this workspace."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            data = c.list_agent_names(ws)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No agents have logged events yet.[/dim]")
        else:
            for name in data:
                console.print(f"  {name}")


@hist_app.command("push")
def hist_push(
    content: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    agent_name: str = typer.Option("cli", "--agent"),
    event_type: str = typer.Option("message", "--type"),
    session_id: str = typer.Option(None, "--session"),
    tool_name: str = typer.Option(None, "--tool"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Push an event to the workspace history."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            data = c.push_event(
                ws,
                agent_name=agent_name,
                event_type=event_type,
                content=content,
                session_id=session_id,
                tool_name=tool_name,
            )
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Event recorded.[/green]  ID: {data['id']}")


@hist_app.command("query")
def hist_query(
    workspace_id: str = typer.Option(None, "--ws"),
    agent_name: str = typer.Option(None, "--agent"),
    event_type: str = typer.Option(None, "--type"),
    limit: int = typer.Option(50, "-n", "--limit"),
    all_: bool = typer.Option(False, "--all"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Query events. --all for cross-workspace."""
    with _client() as c:
        try:
            if all_:
                data = c.all_events(agent_name=agent_name, event_type=event_type, limit=limit)
            else:
                ws = workspace_id or _default_workspace()
                data = c.query_events(ws, agent_name=agent_name, event_type=event_type, limit=limit)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for ev in data:
            tool = f" ({ev['tool_name']})" if ev.get("tool_name") else ""
            console.print(
                f"  [{ev['created_at'][:19]}] {ev['agent_name']}/{ev['event_type']}{tool}: {ev['content'][:200]}"
            )


@hist_app.command("search")
def hist_search(
    query: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    limit: int = typer.Option(50, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Full-text search on events in a workspace."""
    ws = workspace_id or _default_workspace()
    with _client() as c:
        try:
            data = c.search_events(ws, query, limit=limit)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for ev in data:
            console.print(
                f"  [{ev['created_at'][:19]}] {ev['agent_name']}/{ev['event_type']}: {ev['content'][:200]}"
            )


@hist_app.command("transcript")
def hist_transcript(
    session_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    save: str = typer.Option(None, "--save"),
):
    """Fetch a full session transcript (.jsonl) and print or save it.

    Transcripts are stored gzipped on the server; we decompress here so
    `--save` writes plain .jsonl and stdout is readable.
    """
    import gzip

    import httpx

    ws = workspace_id or _default_workspace()
    cfg = load_config()
    url = f"{cfg['base_url'].rstrip('/')}/api/v1/workspaces/{ws}/transcripts/{session_id}"
    headers = {"Authorization": f"Bearer {cfg.get('api_key', '')}"}
    meta = httpx.get(url, headers=headers, timeout=30).json()
    if "download_url" not in meta:
        console.print(f"[red]{meta.get('detail', 'not found')}[/red]")
        raise typer.Exit(1)
    raw = httpx.get(meta["download_url"], timeout=60).content
    # Detect gzip via magic bytes so legacy uncompressed uploads still work.
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    body = raw.decode("utf-8", errors="replace")
    if save:
        Path(save).write_text(body)
        console.print(f"[green]Saved {len(body):,} chars to {save}[/green]")
        return
    sys.stdout.write(body)


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
def tables_list(
    workspace_id: str = typer.Option(None, "--ws"),
    all_: bool = typer.Option(False, "--all"),
    personal: bool = typer.Option(False, "--personal"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List tables. --all for cross-workspace, --personal for personal tables."""
    with _client() as c:
        try:
            if all_:
                data = c.all_tables()
            elif personal:
                data = c.list_personal_tables()
            else:
                data = c.list_tables(workspace_id or _default_workspace())
        except StashError as e:
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
                console.print(
                    f"  {t['name']}{ws}  ({cols} cols, {rows} rows, id: {str(t['id'])[:8]})"
                )


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
        except StashError as e:
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
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Table updated.[/green]")


@tables_app.command("schema")
def tables_schema(
    table_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show a table's column schema."""
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            data = c.get_table(ws, table_id)
        except StashError as e:
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
    filters: str = typer.Option(
        "", "--filter", help='JSON: [{"column_id":"Name","op":"eq","value":"Alice"}]'
    ),
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
            result = c.list_table_rows(
                ws,
                table_id,
                limit=limit,
                offset=offset,
                sort_by=resolved_sort,
                sort_order=sort_order,
                filters=resolved_filters,
            )
        except StashError as e:
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
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print(f"[green]Row inserted.[/green]  ID: {result['id']}")


@tables_app.command("import")
def tables_import(
    table_id: str = typer.Argument(...),
    file: str = typer.Option(
        None, "--file", "-f", help="CSV or JSON file path (or pipe via stdin)"
    ),
    format_: str = typer.Option(
        "auto", "--format", help="csv, json, or auto (detect from extension/content)"
    ),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Bulk import rows from CSV or JSON. Auto-chunks into batches of 5000.
    CSV: first row is column headers. JSON: array of objects.
    Pipe: cat data.csv | stash tables import <table_id> --format csv"""
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
            format_ = (
                "json" if raw_stripped.startswith("[") or raw_stripped.startswith("{") else "csv"
            )
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
                batch = resolved_rows[i : i + batch_size]
                c.insert_table_rows_batch(ws, table_id, batch)
                total_inserted += len(batch)
                if len(resolved_rows) > batch_size:
                    console.print(
                        f"  [dim]Inserted {total_inserted}/{len(resolved_rows)} rows...[/dim]"
                    )
        except StashError as e:
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
        except StashError as e:
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
        except StashError as e:
            _err(e)
    console.print("[green]Row deleted.[/green]")


@tables_app.command("add-column")
def tables_add_column(
    table_id: str = typer.Argument(...),
    name: str = typer.Argument(...),
    col_type: str = typer.Option("text", "--type"),
    options: str = typer.Option(
        "", "--options", help="Comma-separated options for select/multiselect"
    ),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Add a column to a table."""
    opts = [o.strip() for o in options.split(",") if o.strip()] if options else None
    with _client() as c:
        try:
            ws = workspace_id or _default_workspace()
            result = c.add_table_column(ws, table_id, name, col_type=col_type, options=opts)
        except StashError as e:
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
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print("[green]Column deleted.[/green]")


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
        except StashError as e:
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
            resp = c._request(
                "GET", f"/api/v1/workspaces/{ws}/tables/{table_id}/export/csv", params=params
            )
            csv_content = resp.text
        except StashError as e:
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
        except StashError as e:
            _err(e)
    console.print("[green]Table deleted.[/green]")


# ===========================================================================
# Connect wizard
# ===========================================================================


def _reserve_bottom_padding(lines: int = 4) -> None:
    """Scroll the terminal up `lines` rows so prompts don't render flush against the bottom."""
    sys.stdout.write("\n" * lines + f"\033[{lines}A")
    sys.stdout.flush()


def _self_host_walkthrough(cfg: dict) -> str:
    """Walk the user through standing up a local Stash instance, then return its URL."""
    console.print("\n[bold cyan]Self-hosting Stash[/bold cyan]\n")
    console.print("You'll need [bold]Docker[/bold] installed.  https://docker.com/get-started\n")
    console.print("Run these commands in a separate terminal:\n")
    console.print(
        "  [dim]1.[/dim] [cyan]git clone https://github.com/Fergana-Labs/stash.git[/cyan]"
    )
    console.print("  [dim]2.[/dim] [cyan]cd octopus[/cyan]")
    console.print("  [dim]3.[/dim] [cyan]docker compose up -d[/cyan]")
    console.print("\n  [dim]Already running? Skip to the URL prompt below.[/dim]\n")

    _reserve_bottom_padding(6)
    ready = questionary.confirm("Is your instance running?", default=True).ask()
    if ready is None or not ready:
        console.print(
            "\n[yellow]No problem — run [bold]stash connect[/bold] again when ready.[/yellow]"
        )
        raise typer.Exit(0)

    current_url = cfg.get("base_url", "http://localhost:3456")
    managed_hosts = ("https://stash.ac", "https://www.stash.ac", "https://moltchat.onrender.com")
    default_url = "http://localhost:3456" if current_url in managed_hosts else current_url
    return typer.prompt("URL of your instance", default=default_url).rstrip("/")


def _derive_display_name() -> str:
    """Pick a display name with zero interaction: git config → $USER → fallback."""
    import os
    import subprocess

    try:
        out = subprocess.run(
            ["git", "config", "--get", "user.name"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        candidate = out.stdout.strip()
        if candidate:
            return candidate
    except Exception:
        pass
    return os.environ.get("USER") or os.environ.get("USERNAME") or "teammate"


def _connect_via_invite(
    token: str,
    endpoint: str | None,
    scope_flag: str | None,
    display_name_override: str | None,
) -> None:
    """Non-interactive connect path: redeem a magic-link token, save config, show splash.

    Auto-detects whether the user already has a stash account on this machine and
    picks the authenticated or unauthenticated redeem endpoint accordingly. Display
    name is derived from git/$USER so the recipient's coding agent never blocks on
    a prompt.
    """
    cfg = load_config()
    base_url = (endpoint or cfg.get("base_url") or "").rstrip("/")
    if not base_url:
        console.print(
            "[red]--endpoint is required (or run `stash connect` once without --invite first).[/red]"
        )
        raise typer.Exit(1)
    scope = scope_flag or "user"

    existing_key = cfg.get("api_key", "")
    if existing_key:
        # Authenticated redeem — just join the workspace on top of existing identity.
        try:
            with StashClient(base_url=base_url, api_key=existing_key) as c:
                ws = c.redeem_invite_authed(token)
        except StashError as e:
            console.print(f"[red]Could not redeem invite: {e.detail}[/red]")
            raise typer.Exit(1)
        save_config(base_url=base_url, default_workspace=str(ws["id"]), scope=scope)
        _show_setup_complete_splash(workspace_name=ws["name"], joined_via_invite=True)
        return

    # No existing auth — unauthenticated redeem creates a fresh user.
    display_name = (display_name_override or _derive_display_name()).strip()
    try:
        result = StashClient.redeem_invite_unauthenticated(
            base_url=base_url, token=token, display_name=display_name
        )
    except StashError as e:
        console.print(f"[red]Could not redeem invite: {e.detail}[/red]")
        raise typer.Exit(1)

    save_config(
        base_url=base_url,
        api_key=result["api_key"],
        username=result["username"],
        default_workspace=str(result["workspace_id"]),
        scope=scope,
    )
    chosen = result.get("display_name") or result["username"]
    console.print(
        f"  [green]✓[/green] Signed in as [bold]{chosen}[/bold] "
        f"[dim](change with `stash whoami` / profile edit)[/dim]"
    )
    _show_setup_complete_splash(workspace_name=result["workspace_name"], joined_via_invite=True)


@app.command("connect")
def connect(
    welcome: bool = typer.Option(
        False,
        "--welcome",
        help="Print the post-install welcome as plain markdown and exit. For Claude Code / other agents that re-render stdout as markdown.",
    ),
    invite: str = typer.Option(
        None, "--invite", help="Redeem a magic-link invite token (skips the interactive flow)."
    ),
    endpoint: str = typer.Option(
        None, "--endpoint", help="Stash API URL (required with --invite if not already configured)."
    ),
    scope: str = typer.Option(
        None, "--scope", help="Where to write config (user | project). Only used with --invite."
    ),
    display_name: str = typer.Option(
        None,
        "--display-name",
        help="Override the auto-detected display name (default: git config user.name).",
    ),
):
    """Interactive first-time setup. Sets base URL, authenticates, and configures defaults."""
    if welcome:
        print(_WELCOME_MARKDOWN)
        return
    if invite:
        _connect_via_invite(
            token=invite,
            endpoint=endpoint,
            scope_flag=scope,
            display_name_override=display_name,
        )
        return

    console.print("\n[bold]Stash connect[/bold]  (press Enter to accept defaults)\n")

    # --- Manifest detection: runs first so it can steer the later prompts. ---
    manifest = load_manifest()
    if manifest:
        console.print(
            f"  [cyan]Detected .stash/stash.json[/cyan] — this repo is set up for "
            f"[bold]{manifest.get('workspace_name') or 'a stash workspace'}[/bold].\n"
        )

    # --- Step 0: Scope ---
    # With a manifest, we still offer machine-level install; we just flip the
    # default so new contributors land on project scope.
    scope_options = [
        ("Everywhere on this machine", "~/.stash/config.json", "user"),
        ("Only this directory", "./.stash/config.json", "project"),
    ]
    label_width = max(len(label) for label, _, _ in scope_options)
    scope_default_value = "project" if manifest else "user"
    scope_choices = [
        questionary.Choice(f"{label:<{label_width}}   {path}", value=value)
        for label, path, value in scope_options
    ]
    scope_default_choice = next(ch for ch in scope_choices if ch.value == scope_default_value)
    _reserve_bottom_padding(8)
    scope = questionary.select(
        "Where do you want to install stash?",
        choices=scope_choices,
        default=scope_default_choice,
        use_shortcuts=True,
    ).ask()
    if scope is None:
        raise typer.Exit(1)

    # --- Step 1: API endpoint ---
    cfg = load_config()
    if manifest and manifest.get("base_url"):
        base_url = str(manifest["base_url"]).rstrip("/")
        console.print(
            f"  [green]✓[/green] Using endpoint from manifest: [bold]{base_url}[/bold]"
        )
    else:
        mode_options = [
            ("Managed", "hosted by Stash", "managed"),
            ("Self-host", "run on your own machine", "self"),
        ]
        mode_label_w = max(len(label) for label, _, _ in mode_options)
        _reserve_bottom_padding(8)
        mode = questionary.select(
            "How do you want to use Stash?",
            choices=[
                questionary.Choice(f"{label:<{mode_label_w}}   ({desc})", value=value)
                for label, desc, value in mode_options
            ],
            use_shortcuts=True,
        ).ask()
        if mode is None:
            raise typer.Exit(1)

        if mode == "managed":
            base_url = "https://moltchat.onrender.com"
        else:
            base_url = _self_host_walkthrough(cfg)
    save_config(base_url=base_url, scope=scope)

    # --- Step 2: Auth (browser-based) ---
    has_key = bool(cfg.get("api_key"))
    if has_key:
        try:
            with StashClient(base_url=base_url, api_key=cfg["api_key"]) as c:
                user = c.whoami()
            console.print(
                f"  [green]✓[/green] Already authenticated as [bold]{user['name']}[/bold]"
            )
        except StashError:
            has_key = False

    if not has_key:
        import time as _time
        import webbrowser

        import httpx

        # Create a CLI auth session
        try:
            resp = httpx.post(
                f"{base_url}/api/v1/users/cli-auth/sessions",
                timeout=10,
                follow_redirects=True,
            )
            resp.raise_for_status()
            session_id = resp.json()["session_id"]
        except Exception as e:
            console.print(f"[red]Could not reach {base_url}: {e}[/red]")
            raise typer.Exit(1)

        # Build the login URL. The backend and frontend are separate deployments.
        # - Local self-host: backend on :3456, frontend on :3000.
        # - Managed: frontend lives at stash-web-dr40.onrender.com.
        if "localhost" in base_url or "127.0.0.1" in base_url:
            frontend_url = base_url.replace(":3456", ":3000")
        elif base_url == "https://moltchat.onrender.com":
            frontend_url = "https://stash-web-dr40.onrender.com"
        else:
            frontend_url = base_url
        login_url = f"{frontend_url}/login?cli={session_id}"

        console.print("\n  Opening browser to sign in...")
        console.print(f"  [dim]{login_url}[/dim]\n")
        webbrowser.open(login_url)

        _reserve_bottom_padding(4)
        console.print("  Waiting for authentication... [dim](press Ctrl+C to cancel)[/dim]")

        # Poll for the result
        try:
            for _ in range(120):  # 2 minutes max
                _time.sleep(1)
                try:
                    poll = httpx.get(
                        f"{base_url}/api/v1/users/cli-auth/sessions/{session_id}",
                        timeout=5,
                        follow_redirects=True,
                    )
                    if poll.status_code == 200:
                        result = poll.json()
                        if result["status"] == "complete":
                            save_config(api_key=result["api_key"], username=result["username"])
                            console.print(
                                f"  [green]✓[/green] Logged in as [bold]{result['username']}[/bold]"
                            )
                            break
                except httpx.HTTPError:
                    pass
            else:
                console.print("[red]Timed out waiting for authentication.[/red]")
                raise typer.Exit(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled.[/yellow]")
            raise typer.Exit(1)

    # Reload config after auth
    cfg = load_config()

    manifest_joined_ws: str = ""

    with StashClient(base_url=base_url, api_key=cfg["api_key"]) as c:
        if manifest:
            # --- Manifest auto-join path ---
            manifest_ws_id = str(manifest.get("workspace_id") or "")
            manifest_ws_name = str(manifest.get("workspace_name") or "this workspace")
            invite_code = str(manifest.get("invite_code") or "")
            if not manifest_ws_id:
                console.print(
                    "[red]Manifest is missing workspace_id — ask the maintainer to re-run `stash init`.[/red]"
                )
                raise typer.Exit(1)

            already_member = False
            try:
                c.get_workspace(manifest_ws_id)
                already_member = True
            except StashError as e:
                if e.status_code not in (403, 404):
                    _err(e)

            if already_member:
                save_config(default_workspace=manifest_ws_id, scope=scope)
                manifest_joined_ws = manifest_ws_name
                console.print(
                    f"  [green]✓[/green] You're already a member of "
                    f"[bold]{manifest_ws_name}[/bold]. Set as default for this repo."
                )
            else:
                _reserve_bottom_padding(4)
                go = questionary.confirm(
                    f"This repo is set up for the \"{manifest_ws_name}\" workspace on Stash.\n"
                    "  Join and start sharing agent transcripts with the team?",
                    default=True,
                ).ask()
                if go is None:
                    raise typer.Exit(1)

                if not go:
                    # Record an opt-out for this repo (next to the manifest).
                    manifest_path = find_project_manifest()
                    project_path = (
                        manifest_path.parent / PROJECT_FILENAME
                        if manifest_path
                        else find_project_config() or (Path.cwd() / ".stash" / PROJECT_FILENAME)
                    )
                    existing = {}
                    if project_path.exists():
                        try:
                            existing = json.loads(project_path.read_text())
                        except Exception:
                            existing = {}
                    existing["stash_disabled_here"] = True
                    project_path.parent.mkdir(parents=True, exist_ok=True)
                    project_path.write_text(json.dumps(existing, indent=2) + "\n")
                    console.print(
                        "[yellow]Skipped.[/yellow] Hooks in this repo will stay inert. "
                        "Run [cyan]stash enable[/cyan] later to change your mind."
                    )
                else:
                    if not invite_code:
                        console.print(
                            "[red]Manifest has no invite_code — can't join. Ask the maintainer "
                            "to re-run `stash init`.[/red]"
                        )
                        raise typer.Exit(1)
                    try:
                        ws = c.join_workspace(invite_code)
                    except StashError as e:
                        console.print(
                            f"[red]Could not join {manifest_ws_name}: {e.detail}[/red]  "
                            "(invite code may be stale — ask the maintainer to re-run `stash init`.)"
                        )
                        raise typer.Exit(1)
                    joined_name = ws.get("name") or manifest_ws_name
                    save_config(default_workspace=str(ws["id"]), scope=scope)
                    manifest_joined_ws = joined_name
                    console.print(
                        f"  [green]✓[/green] Joined [bold]{joined_name}[/bold]. Set as default for this repo."
                    )
        else:
            # --- Step 3: Workspace (no manifest) ---
            try:
                my_workspaces = c.list_workspaces(mine=True)
            except StashError:
                my_workspaces = []

            workspace_id = cfg.get("default_workspace", "")
            if my_workspaces:
                console.print("\n  Your workspaces:")
                for ws in my_workspaces[:5]:
                    marker = " [dim](current default)[/dim]" if str(ws["id"]) == workspace_id else ""
                    console.print(f"    [dim]{str(ws['id'])[:8]}…[/dim]  {ws['name']}{marker}")

            # Pick a default workspace: prefer the configured one, else the first in the list.
            default_ws = None
            if workspace_id:
                default_ws = next((ws for ws in my_workspaces if str(ws["id"]) == workspace_id), None)
            if not default_ws and my_workspaces:
                default_ws = my_workspaces[0]

            default_name = default_ws["name"] if default_ws else ""

            _reserve_bottom_padding(4)
            ws_name = typer.prompt(
                "\nPress ENTER to accept default workspace name, otherwise type a workspace name",
                default=default_name,
            ).strip()

            if not ws_name:
                console.print("[yellow]Skipping workspace setup.[/yellow]")
            else:
                # If the name matches an existing workspace, reuse it. Otherwise, create a new one.
                matched = next((ws for ws in my_workspaces if ws["name"] == ws_name), None)
                if matched:
                    workspace_id = str(matched["id"])
                    save_config(default_workspace=workspace_id, scope=scope)
                    console.print(f"  [green]✓[/green] Using workspace [bold]{matched['name']}[/bold]")
                else:
                    try:
                        ws_data = c.create_workspace(ws_name)
                        workspace_id = str(ws_data["id"])
                        save_config(default_workspace=workspace_id, scope=scope)
                        console.print(
                            f"  [green]✓[/green] Created workspace [bold]{ws_data['name']}[/bold]  invite: {ws_data['invite_code']}"
                        )
                    except StashError as e:
                        console.print(f"[red]Could not create workspace: {e.detail}[/red]")

    # --- Done ---
    _show_setup_complete_splash(
        workspace_name=manifest_joined_ws,
        joined_via_manifest=bool(manifest_joined_ws),
    )


# ===========================================================================
# Repo-level enablement: stash init / enable / disable
# ===========================================================================


def _git_toplevel(cwd: Path | None = None) -> Path | None:
    """Return the git repo root for `cwd` (or cwd if None). None if not in a repo."""
    import subprocess as _sp

    try:
        out = _sp.run(
            ["git", "-C", str(cwd or Path.cwd()), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    top = out.stdout.strip()
    return Path(top) if top else None


def _looks_public_remote() -> bool:
    """Heuristic for 'this repo's default remote looks public' — used to warn
    on `stash init`. We check GitHub public visibility via `gh` if available;
    otherwise fall back to inspecting `git remote -v` for github.com URLs
    that aren't enterprise hosts. False negatives are OK — the manifest is
    inert until someone runs the CLI, and this is only an advisory warning."""
    import subprocess as _sp

    try:
        out = _sp.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=2)
    except Exception:
        return False
    url = (out.stdout or "").strip()
    if not url or "github.com" not in url:
        return False
    try:
        # Convert git@github.com:owner/repo.git → owner/repo
        owner_repo = url
        if owner_repo.startswith("git@"):
            owner_repo = owner_repo.split(":", 1)[-1]
        elif owner_repo.startswith("https://github.com/"):
            owner_repo = owner_repo[len("https://github.com/"):]
        owner_repo = owner_repo.removesuffix(".git")
        if owner_repo.count("/") != 1:
            return False
        gh = _sp.run(
            ["gh", "api", f"repos/{owner_repo}", "--jq", ".visibility"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if gh.returncode == 0:
            return gh.stdout.strip().lower() == "public"
    except Exception:
        pass
    return False


def _update_gitignore_for_manifest(repo_root: Path) -> str:
    """Ensure `.stash/config.json` is gitignored and `.stash/stash.json` is NOT.
    Returns a short status string for display ('created', 'updated', 'already-set')."""
    gi = repo_root / ".gitignore"
    config_entry = ".stash/config.json"
    manifest_entry = "!.stash/stash.json"

    if not gi.exists():
        gi.write_text(f"{config_entry}\n")
        return "created"

    lines = gi.read_text().splitlines()
    stripped = [line.strip() for line in lines]

    has_wholesale = any(s in (".stash/", ".stash") for s in stripped)
    has_config_entry = any(s == config_entry for s in stripped)
    has_manifest_negation = any(s == manifest_entry for s in stripped)

    if has_config_entry and (not has_wholesale or has_manifest_negation):
        return "already-set"

    new_lines = list(lines)
    if has_wholesale and not has_manifest_negation:
        new_lines.append(manifest_entry)
    if not has_config_entry:
        new_lines.append(config_entry)
    gi.write_text("\n".join(new_lines) + "\n")
    return "updated"


@app.command("init")
def init_cmd():
    """Enable Stash for this repo by writing a committed .stash/stash.json manifest.

    Every teammate who runs `stash connect` in this repo will auto-join the
    workspace pointed to by the manifest.
    """
    repo_root = _git_toplevel()
    if repo_root is None:
        console.print("[red]`stash init` must be run inside a git repo.[/red]")
        raise typer.Exit(1)

    manifest_path = repo_root / ".stash" / "stash.json"
    if manifest_path.exists():
        console.print(
            f"[yellow]This repo already has a manifest at {manifest_path}.[/yellow]  "
            "Edit it directly or `rm` it and re-run `stash init`."
        )
        raise typer.Exit(1)

    cfg = load_config()
    if not cfg.get("api_key"):
        console.print(
            "[red]You need to be signed in first.[/red]  Run [bold]stash connect[/bold] and try again."
        )
        raise typer.Exit(1)

    base_url = (cfg.get("base_url") or "").rstrip("/")
    if not base_url:
        console.print("[red]No base_url configured. Run `stash connect` first.[/red]")
        raise typer.Exit(1)

    with StashClient(base_url=base_url, api_key=cfg["api_key"]) as c:
        try:
            my_workspaces = c.list_workspaces(mine=True)
        except StashError as e:
            _err(e)

        if not my_workspaces:
            console.print(
                "[yellow]You don't own any workspaces yet.[/yellow]  "
                "Create one first: [cyan]stash ws create <name>[/cyan]"
            )
            raise typer.Exit(1)

        default_ws_id = str(cfg.get("default_workspace") or "")
        default_choice = next(
            (ws for ws in my_workspaces if str(ws["id"]) == default_ws_id),
            my_workspaces[0],
        )

        choices = [
            questionary.Choice(
                f"{ws['name']}  [dim]({str(ws['id'])[:8]}…)[/dim]",
                value=str(ws["id"]),
            )
            for ws in my_workspaces
        ]
        _reserve_bottom_padding(6)
        chosen_id = questionary.select(
            "Which workspace should this repo point at?",
            choices=choices,
            default=next(
                (ch for ch in choices if ch.value == str(default_choice["id"])), choices[0]
            ),
            use_shortcuts=True,
        ).ask()
        if chosen_id is None:
            raise typer.Exit(1)

        chosen_ws = next(ws for ws in my_workspaces if str(ws["id"]) == chosen_id)
        invite_code = chosen_ws.get("invite_code") or ""
        if not invite_code:
            # invite_code blanked out by serializer only for non-members; we're the
            # owner so it should always be present. Defensive read otherwise:
            try:
                full = c.get_workspace(chosen_id)
                invite_code = full.get("invite_code") or ""
            except StashError:
                invite_code = ""
        if not invite_code:
            console.print(
                "[red]That workspace has no invite code — can't enable repo-level stash without one.[/red]"
            )
            raise typer.Exit(1)

    manifest: Manifest = {
        "version": 1,
        "workspace_id": str(chosen_ws["id"]),
        "workspace_name": chosen_ws["name"],
        "invite_code": invite_code,
        "base_url": base_url,
        "streaming_default": True,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    gi_status = _update_gitignore_for_manifest(repo_root)

    console.print(
        Panel(
            f"  [bold]Workspace:[/bold]   {chosen_ws['name']}  "
            f"[dim]({str(chosen_ws['id'])[:8]}…)[/dim]\n"
            f"  [bold]Invite code:[/bold] {invite_code}\n"
            f"\n"
            f"  Wrote [cyan]{manifest_path.relative_to(repo_root)}[/cyan]           "
            f"[green]✓[/green]\n"
            f"  .gitignore (.stash/config.json)   [green]{gi_status}[/green]\n"
            f"\n"
            f"  Commit [cyan].stash/stash.json[/cyan] and push. Teammates running "
            f"[cyan]stash connect[/cyan] in this repo will auto-join.",
            title="[bold]Stash init — repo-level enablement[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    if _looks_public_remote():
        console.print(
            "\n[yellow]Heads up:[/yellow] this repo's remote looks public. Anyone who "
            "can clone it can join the workspace via the committed invite code. Only "
            "run [bold]stash init[/bold] on public repos if you want that."
        )


@app.command("enable")
def enable_cmd():
    """Re-enable Stash streaming for this repo (undoes `stash disable`)."""
    manifest_path = find_project_manifest()
    if manifest_path is None:
        console.print(
            "[yellow]No .stash/stash.json found in this repo.[/yellow]  "
            "Ask a maintainer to run [cyan]stash init[/cyan]."
        )
        raise typer.Exit(1)

    project_path = find_project_config() or (manifest_path.parent / PROJECT_FILENAME)
    existing = {}
    if project_path.exists():
        try:
            existing = json.loads(project_path.read_text())
        except Exception:
            existing = {}
    existing.pop("stash_disabled_here", None)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(json.dumps(existing, indent=2) + "\n")
    console.print(f"[green]Stash streaming enabled for this repo.[/green]  ({project_path})")


@app.command("disable")
def disable_cmd():
    """Stop streaming for this repo without touching the committed manifest."""
    manifest_path = find_project_manifest()
    if manifest_path is None:
        console.print(
            "[yellow]No .stash/stash.json found in this repo.[/yellow]  "
            "Nothing to disable."
        )
        raise typer.Exit(1)

    project_path = find_project_config() or (manifest_path.parent / PROJECT_FILENAME)
    existing = {}
    if project_path.exists():
        try:
            existing = json.loads(project_path.read_text())
        except Exception:
            existing = {}
    existing["stash_disabled_here"] = True
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(json.dumps(existing, indent=2) + "\n")
    console.print(
        f"[yellow]Stash streaming disabled for this repo.[/yellow]  ({project_path})\n"
        "Run [cyan]stash enable[/cyan] to turn it back on."
    )


STASH_LOGO = r"""
 ███████╗████████╗ █████╗ ███████╗██╗  ██╗
 ██╔════╝╚══██╔══╝██╔══██╗██╔════╝██║  ██║
 ███████╗   ██║   ███████║███████╗███████║
 ╚════██║   ██║   ██╔══██║╚════██║██╔══██║
 ███████║   ██║   ██║  ██║███████║██║  ██║
 ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
"""


_WELCOME_MARKDOWN = """# You're all set up.

## What just happened

Your coding agent now has the `stash` CLI on its PATH. It can read the transcripts your teammates' coding agents push to this workspace — so it knows what the rest of your team is working on.

## Examples of questions your agent might want answered

- "Why did Sam bump the rate limit from 100 to 500?"
- "Has anyone already tried fixing the memory leak in our backend?"
- "Is anyone else currently working on our api gateway?"

You can read a blog post about it here: [Agent velocity for coding teams](https://henrydowling.com/agent-velocity.html)

## Commands your agent can now use

- `stash history search "<query>"` — full-text search across transcripts
- `stash history query --agent <name>` — pull a specific agent's events

Run `stash --help` to see everything.

## Q&A

**Q:** Do you inject anything into my coding agent's context automatically?
**A:** No.

**Q:** What gets pushed to the shared store?
**A:** For sessions in this repo (and its worktrees): prompts, assistant replies, summarized tool activity, and the full session transcript (.jsonl) at session end. Other repos push nothing unless you widen scope. Transcripts are stored verbatim — no secret scrubbing yet.

**Q:** How do I change scope or see a transcript?
**A:** `stash config scope <repo|workspace|all>` (default: `repo`). `stash history transcript <session_id>` fetches a full transcript.

**Q:** How do I share my workspace with my team?
**A:** Share the invite code (`stash workspaces info <id>` prints it). Teammates run `stash connect` if needed, then `stash workspaces join <invite_code>`.
"""


def _capture_install_repo() -> None:
    """At connect time, remember the git common-dir of this repo so the
    plugins can scope uploads to it (and its worktrees). If cwd isn't in a
    git repo, prompt the user to pick scope=all or skip uploads entirely."""
    import subprocess as _sp

    common = ""
    for args in (
        ["git", "-C", str(Path.cwd()), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        ["git", "-C", str(Path.cwd()), "rev-parse", "--git-common-dir"],
    ):
        try:
            out = _sp.run(args, capture_output=True, text=True, timeout=2)
        except Exception:
            continue
        if out.returncode == 0 and out.stdout.strip():
            common = out.stdout.strip()
            if not Path(common).is_absolute():
                common = str(Path.cwd() / common)
            break

    central = _read_central_config()
    if common:
        updates = {"install_repo_common_dir": common}
        if "scope" not in central:
            updates["scope"] = "repo"
        _write_central_config(updates)
        return
    if central.get("install_repo_common_dir"):
        return
    console.print(
        "\n[yellow]Not inside a git repo.[/yellow] Uploads are scoped to the install "
        "repo by default; with none captured, nothing will upload."
    )
    if typer.confirm("Upload from everywhere? (scope=all)", default=False):
        _write_central_config({"scope": "all"})
    else:
        _write_central_config({"scope": "repo"})


def _show_setup_complete_splash(
    workspace_name: str = "",
    joined_via_invite: bool = False,
    joined_via_manifest: bool = False,
) -> None:
    """Clear the onboarding transcript and show a clean success splash."""
    _capture_install_repo()
    console.clear()
    console.print(f"[bold cyan]{STASH_LOGO}[/bold cyan]")
    if (joined_via_invite or joined_via_manifest) and workspace_name:
        console.print(f"  [bold green]You joined[/bold green] [bold]{workspace_name}[/bold].\n")
    else:
        console.print("  [bold green]You're all set up.[/bold green]\n")

    body = (
        "[bold]What just happened[/bold]\n"
        "Your coding agent now has the [bold cyan]stash[/bold cyan] CLI on its PATH.\n"
        "It can read the transcripts your teammates' coding agents push to this\n"
        "workspace — so it knows what the rest of your team is working on.\n"
        "\n"
        "[bold]Examples of questions your agent might want answered [/bold] \n"
        '  [dim]"Why did Sam bump the rate limit from 100 to 500?"[/dim]\n'
        '  [dim]"Has anyone already tried fixing the memory leak in our backend?"[/dim]\n'
        '  [dim]"Is anyone else currently working on our api gateway"[/dim]\n'
        "\n"
        "  You can read a blog post about it here: "
        "[link=https://henrydowling.com/agent-velocity.html]Agent velocity for coding teams[/link]\n"
        "\n"
        "[bold]Commands your agent can now use[/bold]\n"
        '  [cyan]stash history search "<query>"[/cyan]   full-text search across transcripts\n'
        "  [cyan]stash history query --agent <name>[/cyan]   pull a specific agent's events\n"
        "\n"
        "Run [bold]stash --help[/bold] to see everything.\n"
        "\n"
        "[bold]Q&A[/bold]\n"
        "  [bold]Q[/bold] Do you inject anything into my coding agent's context automatically?\n"
        "  [bold]A[/bold] No.\n"
        "\n"
        "  [bold]Q[/bold] What gets pushed to the shared store?\n"
        "  [bold]A[/bold] For sessions in this repo (and its worktrees): prompts, assistant\n"
        "     replies, summarized tool activity, and the full session transcript (.jsonl)\n"
        "     at session end. Other repos push nothing unless you widen scope.\n"
        "     [yellow]Transcripts are stored verbatim[/yellow] — no secret scrubbing yet.\n"
        "\n"
        "  [bold]Q[/bold] How do I change scope or see a transcript?\n"
        "  [bold]A[/bold] [cyan]stash config scope <repo|workspace|all>[/cyan]  (default: repo)\n"
        "     [cyan]stash history transcript <session_id>[/cyan]  view a full transcript\n"
        '     [cyan]stash history search "<query>"[/cyan]         search event content\n'
        "\n"
        "  [bold]Q[/bold] How do I share my workspace with my team?\n"
        "  [bold]A[/bold] Share the invite code ([cyan]stash workspaces info <id>[/cyan] prints it).\n"
        "     Teammates run [cyan]stash connect[/cyan] if needed, then\n"
        "     [cyan]stash workspaces join <invite_code>[/cyan].\n"
    )
    console.print(
        Panel(
            body,
            title="[bold]Your team's shared agent memory[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    if (joined_via_invite or joined_via_manifest) and workspace_name:
        if joined_via_manifest:
            joined_body = (
                f"You joined [bold]{workspace_name}[/bold] via this repo's "
                "[cyan].stash/stash.json[/cyan] manifest.\n"
                "Your agent now pushes transcripts for work in this repo to the team's\n"
                "shared memory. Try one of these:\n"
                "\n"
                "  [cyan]stash history agents[/cyan]           who's been active in this workspace\n"
                '  [cyan]stash history search "<query>"[/cyan]   full-text search across transcripts\n'
                "  [cyan]stash disable[/cyan]                  opt this repo out without touching the manifest"
            )
        else:
            joined_body = (
                f"You're now a member of [bold]{workspace_name}[/bold] and your default\n"
                "workspace is set. Try one of these to see what your teammates are up to:\n"
                "\n"
                "  [cyan]stash history agents[/cyan]           who's been active in this workspace\n"
                '  [cyan]stash history search "<query>"[/cyan]   full-text search across transcripts\n'
                "  [cyan]stash history query --limit 20[/cyan]    latest events in your new workspace"
            )
        console.print(
            Panel(
                joined_body,
                title=f"[bold]Welcome to {workspace_name}[/bold]",
                border_style="green",
                padding=(1, 2),
            )
        )

    console.print()


# ===========================================================================
# Plugin control (agent-agnostic — applies to every installed plugin)
# ===========================================================================

PLUGIN_DATA_DIRS = {
    "claude": Path.home() / ".claude/plugins/data/stash",
    "codex": Path.home() / ".stash/plugins/codex",
    "cursor": Path.home() / ".stash/plugins/cursor",
    "gemini": Path.home() / ".stash/plugins/gemini",
    "opencode": Path.home() / ".stash/plugins/opencode",
}


@app.command("status")
def status(as_json: bool = typer.Option(False, "--json")):
    """Show central Stash config, streaming state, and last curate run."""
    cfg = load_config()
    central = _read_central_config()

    display_cfg = dict(cfg)
    if display_cfg.get("api_key"):
        display_cfg["api_key"] = display_cfg["api_key"][:10] + "..."

    streaming_enabled = bool(central.get("streaming_enabled", True))
    auto_curate = bool(central.get("auto_curate", True))
    last_curate_at = central.get("last_curate_at")
    scope = (central.get("scope") or "repo").strip().lower()
    install_repo = central.get("install_repo_common_dir") or ""

    plugins_seen = [name for name, d in PLUGIN_DATA_DIRS.items() if d.exists()]

    if as_json or cfg.get("output_format") == "json":
        output_json(
            {
                "config": display_cfg,
                "streaming_enabled": streaming_enabled,
                "auto_curate": auto_curate,
                "last_curate_at": last_curate_at,
                "plugins_installed": plugins_seen,
                "scope": scope,
                "install_repo_common_dir": install_repo,
            }
        )
        return

    console.print("[bold]Stash status[/bold]")
    console.print(f"  User:       {cfg.get('username') or '(not logged in)'}")
    console.print(f"  Endpoint:   {cfg.get('base_url')}")
    console.print(f"  Workspace:  {cfg.get('default_workspace') or '(none)'}")
    console.print(f"  Store:      {cfg.get('default_store') or '(none)'}")
    console.print(
        f"  Streaming:  {'enabled' if streaming_enabled else '[yellow]disabled[/yellow]'}"
    )
    console.print(f"  Auto-curate: {'on' if auto_curate else 'off'}")
    if last_curate_at:
        import datetime as _dt

        ts = _dt.datetime.fromtimestamp(float(last_curate_at)).isoformat(timespec="seconds")
        console.print(f"  Last curate: {ts}")
    else:
        console.print("  Last curate: (never)")
    console.print(f"  Plugins installed: {', '.join(plugins_seen) or '(none detected)'}")
    console.print(f"  Scope:      {scope}")
    if scope == "repo":
        console.print(f"  Install repo: {install_repo or '(none)'}")


@app.command("disconnect")
def disconnect(as_json: bool = typer.Option(False, "--json")):
    """Pause activity streaming across every installed plugin."""
    _write_central_config({"streaming_enabled": False})
    if as_json or load_config().get("output_format") == "json":
        output_json({"streaming_enabled": False})
        return
    console.print("[yellow]Streaming disabled.[/yellow] Hooks will stop pushing events.")
    console.print(
        "  Re-enable with [bold]stash connect[/bold] or edit [cyan]~/.stash/config.json[/cyan]."
    )


def _read_central_config() -> dict:
    from .config import USER_CONFIG_FILE

    if not USER_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(USER_CONFIG_FILE.read_text())
    except Exception:
        return {}


def _write_central_config(updates: dict) -> None:
    from .config import USER_CONFIG_FILE

    existing = _read_central_config()
    existing.update(updates)
    USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = USER_CONFIG_FILE.with_suffix(USER_CONFIG_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(existing, indent=2) + "\n")
    tmp.replace(USER_CONFIG_FILE)


# ===========================================================================
# Config
# ===========================================================================


@app.command("config")
def config_cmd(
    key: str | None = typer.Argument(None),
    value: str | None = typer.Argument(None),
    project: bool = typer.Option(
        False, "--project", help="Write to project-level config (.stash/config.json in the repo)."
    ),
):
    """Show or set config. Keys: base_url, default_workspace, output_format.

    By default writes to ~/.stash/config.json. Pass --project to write to
    .stash/config.json in the current project (created if missing). Project
    config overrides user config when both exist.
    """
    from .config import USER_CONFIG_FILE, find_project_config

    if key and value:
        if key == "scope":
            if value not in {"repo", "workspace", "all"}:
                console.print("[red]Invalid scope. Must be: repo | workspace | all[/red]")
                raise typer.Exit(1)
            _write_central_config({"scope": value})
            console.print(f"[green]scope = {value}[/green]")
            return
        write_scope = "project" if project else "user"
        allowed = {
            "base_url",
            "default_workspace",
            "default_chat",
            "output_format",
        }
        if key not in allowed and key not in {"api_key", "username"}:
            console.print(f"[red]Unknown config key: {key}[/red]")
            raise typer.Exit(1)
        save_config(**{key: value, "scope": write_scope})
        console.print(f"[green]{key} = {value}[/green]  [dim](scope: {write_scope})[/dim]")
        return

    cfg = load_config()
    display = dict(cfg)
    if display.get("api_key"):
        display["api_key"] = display["api_key"][:10] + "..."

    project_path = find_project_config()
    console.print(f"[dim]user:    {USER_CONFIG_FILE}[/dim]")
    console.print(f"[dim]project: {project_path or '(none — project config not set)'}[/dim]\n")
    console.print(json.dumps(display, indent=2, default=str))


if __name__ == "__main__":
    app()
