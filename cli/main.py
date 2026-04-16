"""Stash CLI — command-line interface for workspaces, notebooks, tables, history, and search."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import questionary
import typer

from .client import StashClient, StashError
from .config import load_config, save_config
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
    console.print("  [dim]1.[/dim] [cyan]git clone https://github.com/Fergana-Labs/octopus.git[/cyan]")
    console.print("  [dim]2.[/dim] [cyan]cd octopus[/cyan]")
    console.print("  [dim]3.[/dim] [cyan]docker compose up -d[/cyan]")
    console.print("\n  [dim]Already running? Skip to the URL prompt below.[/dim]\n")

    _reserve_bottom_padding(6)
    ready = questionary.confirm("Is your instance running?", default=True).ask()
    if ready is None or not ready:
        console.print("\n[yellow]No problem — run [bold]stash connect[/bold] again when ready.[/yellow]")
        raise typer.Exit(0)

    current_url = cfg.get("base_url", "http://localhost:3456")
    managed_hosts = ("https://stash.ac", "https://www.stash.ac", "https://moltchat.onrender.com")
    default_url = "http://localhost:3456" if current_url in managed_hosts else current_url
    return typer.prompt("URL of your instance", default=default_url).rstrip("/")



@app.command("connect")
def connect():
    """Interactive first-time setup. Sets base URL, authenticates, and configures defaults."""
    console.print("\n[bold]Stash connect[/bold]  (press Enter to accept defaults)\n")

    # --- Step 0: Scope ---
    scope_options = [
        ("Everywhere on this machine (default)", "~/.stash/config.json", "user"),
        ("Only this directory", "./.stash/config.json", "project"),
    ]
    label_width = max(len(label) for label, _, _ in scope_options)
    _reserve_bottom_padding(8)
    scope = questionary.select(
        "Where do you want to install stash?",
        choices=[
            questionary.Choice(f"{label:<{label_width}}   {path}", value=value)
            for label, path, value in scope_options
        ],
        use_shortcuts=True,
    ).ask()
    if scope is None:
        raise typer.Exit(1)

    # --- Step 1: API endpoint ---
    cfg = load_config()
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

        console.print(f"\n  Opening browser to sign in...")
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
                            console.print(f"  [green]✓[/green] Logged in as [bold]{result['username']}[/bold]")
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

    with StashClient(base_url=base_url, api_key=cfg["api_key"]) as c:
        # --- Step 3: Workspace ---
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

        ws_action = typer.prompt(
            "\nUse existing workspace ID, or type a name to create new one",
            default=workspace_id or "",
        ).strip()

        if not ws_action:
            console.print(
                "[yellow]Skipping workspace setup. Run: stash config default_workspace <id>[/yellow]"
            )
        else:
            # Check if it looks like a UUID (existing) or a name (create new)
            import re

            is_uuid = bool(re.match(r"^[0-9a-f-]{32,36}$", ws_action, re.I))
            if is_uuid:
                workspace_id = ws_action
                save_config(default_workspace=workspace_id, scope=scope)
                console.print(
                    f"  [green]✓[/green] Default workspace set to [bold]{workspace_id[:8]}…[/bold]"
                )
            else:
                try:
                    ws_data = c.create_workspace(ws_action)
                    workspace_id = str(ws_data["id"])
                    save_config(default_workspace=workspace_id, scope=scope)
                    console.print(
                        f"  [green]✓[/green] Created workspace [bold]{ws_data['name']}[/bold]  invite: {ws_data['invite_code']}"
                    )
                except StashError as e:
                    console.print(f"[red]Could not create workspace: {e.detail}[/red]")

    # --- Done ---
    console.print("\n[bold green]Setup complete.[/bold green]")
    console.print("  Run [bold]stash whoami[/bold] to confirm auth.")
    console.print('  Run [bold]stash history push "hello"[/bold] to push your first event.')
    console.print("  Run [bold]stash --help[/bold] to see all commands.\n")


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

    plugins_seen = [name for name, d in PLUGIN_DATA_DIRS.items() if d.exists()]

    if as_json or cfg.get("output_format") == "json":
        output_json(
            {
                "config": display_cfg,
                "streaming_enabled": streaming_enabled,
                "auto_curate": auto_curate,
                "last_curate_at": last_curate_at,
                "plugins_installed": plugins_seen,
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
        scope = "project" if project else "user"
        allowed = {
            "base_url",
            "default_workspace",
            "default_chat",
            "output_format",
        }
        if key not in allowed and key not in {"api_key", "username"}:
            console.print(f"[red]Unknown config key: {key}[/red]")
            raise typer.Exit(1)
        save_config(**{key: value, "scope": scope})
        target = "project" if project else "user"
        console.print(f"[green]{key} = {value}[/green]  [dim](scope: {target})[/dim]")
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
