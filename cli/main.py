"""Stash CLI — command-line interface for workspaces, notebooks, tables, history, and search."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import questionary
import typer
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .client import StashClient, StashError
from .config import (
    PROJECT_FILENAME,
    Manifest,
    detect_previous_scope,
    find_project_config,
    find_project_manifest,
    load_config,
    load_manifest,
    save_config,
    stored_base_url,
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


def _default_signin_page(api: str) -> str:
    """Map a backend URL to its matching /connect-token page."""
    api = api.rstrip("/")
    if api in ("https://api.stash.ac",):
        return "https://stash.ac/connect-token"
    if "localhost" in api or "127.0.0.1" in api:
        # Local self-host: backend on :3456, frontend on :3457.
        return api.replace(":3456", ":3457") + "/connect-token"
    return api + "/connect-token"


def _browser_auth_flow(
    api: str,
    page: str | None = None,
    timeout: int = 120,
    no_browser: bool = False,
) -> tuple[str, str]:
    """Browser-based CLI sign-in. Returns (api_key, username).

    Creates a short-lived session on the backend, opens the /connect-token
    page with the session id, then polls until the browser posts the minted
    API key back. Raises typer.Exit on failure or timeout. Caller is
    responsible for persisting the returned credentials.
    """
    import os
    import socket
    import time
    import webbrowser
    from urllib.parse import quote

    import httpx

    page = page or _default_signin_page(api)
    device_name = socket.gethostname() or ""

    with httpx.Client(base_url=api, timeout=10) as c:
        try:
            r = c.post(
                "/api/v1/users/cli-auth/sessions", json={"device_name": device_name}
            )
            r.raise_for_status()
            session_id = r.json()["session_id"]
        except (httpx.HTTPError, KeyError) as e:
            console.print(f"[red]Could not reach {api}: {e}[/red]")
            raise typer.Exit(1)

    sep = "&" if "?" in page else "?"
    url = f"{page}{sep}session={session_id}"
    if device_name:
        url += f"&device={quote(device_name)}"

    ssh = any(os.environ.get(v) for v in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))
    opened = False if (no_browser or ssh) else webbrowser.open(url)

    if opened:
        console.print(f"  [green]✓[/green] Opened [bold]{page}[/bold] in your browser.")
    else:
        console.print(f"  Open this URL on your local machine:\n    [bold]{url}[/bold]")

    console.print(f"  Waiting for sign-in (timeout {timeout}s)…")

    deadline = time.monotonic() + timeout
    with httpx.Client(base_url=api, timeout=10) as c:
        while time.monotonic() < deadline:
            try:
                r = c.get(f"/api/v1/users/cli-auth/sessions/{session_id}")
                r.raise_for_status()
                data = r.json()
            except httpx.HTTPError as e:
                console.print(f"[red]Polling failed: {e}[/red]")
                raise typer.Exit(1)
            if data.get("status") == "complete":
                return data["api_key"], data["username"]
            time.sleep(1)

    console.print(
        f"[red]Timed out waiting for sign-in.[/red] "
        f"Run [cyan]stash auth {api} --api-key <token>[/cyan] by hand if needed."
    )
    raise typer.Exit(1)


@app.command()
def signin(
    page: str = typer.Option(
        None,
        "--page",
        help="Sign-in page URL. Defaults to the /connect-token page matching --api.",
    ),
    api: str = typer.Option(
        "https://api.stash.ac",
        "--api",
        help="Stash API base URL. Override for self-hosted deployments.",
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Skip auto-opening the browser; just print the URL. Use when on SSH or without a display.",
    ),
    timeout: int = typer.Option(120, "--timeout", help="Seconds to wait for sign-in."),
):
    """Sign in through the browser — blocks until the user authorizes.

    Writes credentials to `~/.stash/config.json` on success and auto-selects
    the default workspace if the user has exactly one.
    """
    api_key, username = _browser_auth_flow(api, page, timeout, no_browser)
    save_config(base_url=api, api_key=api_key, username=username)
    console.print(f"[green]✓ Signed in as {username}[/green]")

    # Auto-select default workspace if the user has exactly one.
    if load_config().get("default_workspace"):
        return
    try:
        with StashClient(base_url=api, api_key=api_key) as client:
            workspaces = client.list_workspaces(mine=True)
    except StashError:
        return
    if len(workspaces) == 1:
        ws = workspaces[0]
        save_config(default_workspace=str(ws["id"]))
        console.print(f"  Default workspace set to [bold]{ws['name']}[/bold]")


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
            return
        # Auto-set default workspace when the user has exactly one and none is
        # configured yet — otherwise a fresh `stash auth` leaves new users in a
        # state where every command needing workspace context (`stash history`,
        # plugin SessionEnd hooks) errors with "no default workspace". Don't
        # touch an existing default; multi-workspace users still need to pick
        # explicitly via `stash workspaces use`.
        if load_config().get("default_workspace"):
            return
        try:
            workspaces = c.list_workspaces(mine=True)
        except StashError:
            return
        if len(workspaces) == 1:
            ws = workspaces[0]
            save_config(default_workspace=str(ws["id"]))
            console.print(f"  Default workspace set to [bold]{ws['name']}[/bold]")


# ===========================================================================
# Install — wire up hook plugins for every coding agent on PATH
# ===========================================================================

_SUPPORTED_AGENTS = ("claude", "cursor", "codex", "opencode")

_AGENT_BINARY = {
    "claude": "claude",
    "cursor": "cursor-agent",
    "codex": "codex",
    "opencode": "opencode",
}


def _detected_agents() -> list[str]:
    import shutil

    return [a for a in _SUPPORTED_AGENTS if shutil.which(_AGENT_BINARY[a])]


def _entry_references(obj: object, needle: str) -> bool:
    """True if any string anywhere in `obj` contains `needle`."""
    if isinstance(obj, dict):
        return any(_entry_references(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_entry_references(v, needle) for v in obj)
    if isinstance(obj, str):
        return needle in obj
    return False


def _merge_json_hooks(dest: Path, template: str, plugin_root: Path) -> str:
    """Merge stash hook entries into a JSON hooks file under each event array.

    Stash-owned entries are identified by the PLUGIN_ROOT path embedded in their
    command strings — so re-runs replace our entries in place and never touch
    user-added entries. Returns 'installed', 'skipped', or 'failed'.
    """
    from string import Template

    root_str = str(plugin_root)
    rendered = Template(template).safe_substitute(PLUGIN_ROOT=root_str)
    try:
        tmpl_data = json.loads(rendered)
    except json.JSONDecodeError:
        return "failed"

    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(tmpl_data, indent=2) + "\n")
        return "installed"

    try:
        existing = json.loads(dest.read_text())
    except json.JSONDecodeError:
        return "failed"

    tmpl_hooks = tmpl_data.get("hooks", {})
    existing_hooks = existing.setdefault("hooks", {})
    changed = False
    for event, tmpl_entries in tmpl_hooks.items():
        if not isinstance(tmpl_entries, list):
            continue
        cur = existing_hooks.get(event) or []
        if not isinstance(cur, list):
            cur = []
        user_entries = [e for e in cur if not _entry_references(e, root_str)]
        merged = user_entries + tmpl_entries
        if merged != cur:
            changed = True
        existing_hooks[event] = merged

    if not changed:
        return "skipped"

    dest.write_text(json.dumps(existing, indent=2) + "\n")
    return "installed"


def _install_claude(force: bool) -> tuple[str, str]:
    # Delegates to the canonical helper used by `stash connect`. Both
    # `claude plugin marketplace add` and `claude plugin install` are idempotent
    # so --force doesn't need to change behavior.
    ok = _install_claude_plugin()
    if ok:
        return ("installed", "claude plugin installed via marketplace")
    return ("failed", "claude plugin install; see inline output")


def _install_cursor(force: bool) -> tuple[str, str]:
    from stashai.plugin.assets import assets_dir

    root = assets_dir("cursor")
    dest = Path.home() / ".cursor" / "hooks.json"
    template = (root / "hooks.json").read_text()
    status_ = _merge_json_hooks(dest, template, root)
    return (status_, f"{dest}")


_CODEX_MARKER = "# stash-plugin"


def _install_codex(force: bool) -> tuple[str, str]:
    from stashai.plugin.assets import assets_dir

    root = assets_dir("codex")
    hooks_dest = Path.home() / ".codex" / "hooks.json"
    template = (root / "hooks.json").read_text()
    status_ = _merge_json_hooks(hooks_dest, template, root)

    # Append config.toml snippet idempotently via marker line.
    from string import Template

    cfg_path = Path.home() / ".codex" / "config.toml"
    snippet = Template((root / "config.toml.snippet").read_text()).safe_substitute(
        PLUGIN_ROOT=str(root)
    )
    existing = cfg_path.read_text() if cfg_path.exists() else ""
    if _CODEX_MARKER not in existing:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with cfg_path.open("a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"\n{_CODEX_MARKER}\n{snippet}\n")
    return (status_, f"{hooks_dest} + merged {cfg_path}")


def _install_opencode(force: bool) -> tuple[str, str]:
    from stashai.plugin.assets import assets_dir

    root = assets_dir("opencode")
    plugin_path = str(root / "plugin.ts")
    cfg_path = Path.home() / ".config" / "opencode" / "opencode.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            return ("failed", f"{cfg_path} is not valid JSON; fix by hand")

    plugins = cfg.get("plugin", [])
    if plugin_path in plugins and not force:
        return ("skipped", f"{cfg_path} already references plugin.ts")
    plugins = [p for p in plugins if p != plugin_path]
    plugins.append(plugin_path)
    cfg["plugin"] = plugins
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return ("installed", f"{cfg_path} (plugin entry added)")


_INSTALLERS = {
    "claude": _install_claude,
    "cursor": _install_cursor,
    "codex": _install_codex,
    "opencode": _install_opencode,
}


def _plugin_installed(agent: str) -> bool:
    """Best-effort check: did the stash plugin installer already run for this agent?"""
    if agent == "claude":
        registry = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
        if not registry.exists():
            return False
        try:
            data = json.loads(registry.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        return "stash@stash-plugins" in (data.get("plugins") or {})
    if agent == "cursor":
        return (Path.home() / ".cursor" / "hooks.json").exists()
    if agent == "codex":
        toml_path = Path.home() / ".codex" / "config.toml"
        if not toml_path.exists():
            return False
        try:
            return _CODEX_MARKER in toml_path.read_text()
        except OSError:
            return False
    if agent == "opencode":
        cfg_path = Path.home() / ".config" / "opencode" / "opencode.json"
        if not cfg_path.exists():
            return False
        try:
            cfg = json.loads(cfg_path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        from stashai.plugin.assets import assets_dir

        expected = str(assets_dir("opencode") / "plugin.ts")
        return expected in (cfg.get("plugin") or [])
    return False


@app.command("install")
def install_cmd(
    agents: list[str] = typer.Argument(
        None,
        help="Agent(s) to install for. Defaults to every supported agent on $PATH.",
    ),
    skip: str = typer.Option(
        "", "--skip", help="Comma-separated agents to exclude (e.g. --skip codex,opencode)."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing hook files."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Install Stash hook plugins for every supported coding agent on `$PATH`.

    Idempotent — re-running is a no-op unless `--force`.
    """
    skip_set = {s.strip() for s in skip.split(",") if s.strip()}

    if agents:
        unknown = [a for a in agents if a not in _SUPPORTED_AGENTS]
        if unknown:
            console.print(f"[red]Unknown agents: {', '.join(unknown)}[/red]")
            raise typer.Exit(1)
        targets = agents
    else:
        targets = _detected_agents()

    targets = [a for a in targets if a not in skip_set]

    if not targets:
        console.print(
            "[yellow]No supported coding agents detected on PATH.[/yellow] "
            "Install claude / cursor-agent / codex / opencode, then re-run."
        )
        raise typer.Exit(1)

    results: dict[str, dict] = {}
    for agent in targets:
        try:
            status_, detail = _INSTALLERS[agent](force)
        except Exception as e:
            status_, detail = ("failed", f"{type(e).__name__}: {e}")
        results[agent] = {"status": status_, "detail": detail}

    if _use_json(as_json):
        output_json(results)
        return

    for agent, r in results.items():
        color = {"installed": "green", "skipped": "yellow", "failed": "red"}[r["status"]]
        console.print(f"  [{color}]{r['status']:9}[/{color}] {agent:8} {r['detail']}")

    any_failed = any(r["status"] == "failed" for r in results.values())
    if any_failed:
        raise typer.Exit(1)


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


@ws_app.command("use")
def ws_use(
    workspace: str = typer.Argument(..., help="Workspace ID or name to set as default."),
    scope: str = typer.Option(
        "user", "--scope", help="Where to write config (user | project)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Set the default workspace for future commands.

    Resolves `workspace` against the caller's memberships — accepts either a
    workspace ID (UUID) or a name. Non-interactive: designed for agents that
    collect the choice via their own prompting and need a single command to
    persist it.
    """
    with _client() as c:
        try:
            mine = c.list_workspaces(mine=True)
        except StashError as e:
            _err(e)
    match = next(
        (w for w in mine if str(w["id"]) == workspace or w.get("name") == workspace),
        None,
    )
    if not match:
        console.print(
            f"[red]No workspace matches '{workspace}'.[/red] "
            f"Run [cyan]stash workspaces list --mine[/cyan] to see yours."
        )
        raise typer.Exit(1)
    save_config(default_workspace=str(match["id"]), scope=scope)  # type: ignore[arg-type]
    if _use_json(as_json):
        output_json({"default_workspace": str(match["id"]), "name": match["name"]})
    else:
        console.print(
            f"[green]Default workspace set to '{match['name']}'[/green]  (ID: {match['id']})"
        )


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
    console.print("  [dim]2.[/dim] [cyan]cd stash[/cyan]")
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
    managed_hosts = ("https://stash.ac", "https://www.stash.ac", "https://api.stash.ac")
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


def _already_fully_connected(manifest: Manifest | None) -> bool:
    """If every setting `stash connect` touches is already configured and valid,
    print a short summary and return True so the caller can short-circuit.
    Otherwise return False and fall through to the interactive flow.
    """
    prev_scope = detect_previous_scope()
    prev_base = stored_base_url()
    cfg = load_config()
    api_key = cfg.get("api_key", "")
    default_ws = cfg.get("default_workspace", "")
    if not (prev_scope and prev_base and api_key and default_ws):
        return False
    # In a manifest repo, short-circuit only if the configured default workspace
    # matches the manifest's workspace — otherwise we still need to join.
    if manifest and str(manifest.get("workspace_id") or "") not in ("", default_ws):
        return False

    try:
        with StashClient(base_url=prev_base, api_key=api_key) as c:
            user = c.whoami()
            ws = c.get_workspace(default_ws)
    except StashError:
        return False

    detected = _detected_agents()
    if not all(_plugin_installed(a) for a in detected):
        return False

    agent_label = {
        "claude": "Claude Code",
        "cursor": "Cursor",
        "codex": "Codex",
        "opencode": "opencode",
    }
    managed_hosts = ("https://stash.ac", "https://www.stash.ac", "https://api.stash.ac")
    endpoint_label = "Managed" if prev_base in managed_hosts else prev_base
    console.print(
        f"  [green]✓[/green] Already connected to [bold]{ws['name']}[/bold] as "
        f"[bold]{user['name']}[/bold]."
    )
    console.print(f"    [dim]Endpoint:[/dim]  {endpoint_label}")
    if detected:
        console.print(
            f"    [dim]Plugins:[/dim]   {', '.join(agent_label[a] for a in detected)}"
        )
    console.print(
        "\n  Run [cyan]stash settings[/cyan] to tweak, or [cyan]stash disconnect[/cyan] to reset.\n"
    )
    return True


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
        print(_welcome_markdown())
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

    if _already_fully_connected(manifest):
        return

    # --- Step 0: Scope ---
    # Preserve the previous choice on re-runs so `stash connect` doesn't
    # overwrite a directory-scoped install with a machine-wide one (or vice
    # versa). With a manifest, we still offer machine-level install; we just
    # flip the default so new contributors land on project scope.
    prev_scope = detect_previous_scope()
    if prev_scope:
        scope = prev_scope
        scope_label = (
            "everywhere on this machine" if scope == "user" else "only this directory"
        )
        console.print(
            f"  [green]✓[/green] Using existing scope: [bold]{scope_label}[/bold]"
        )
    else:
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
    prev_base = stored_base_url()
    if manifest and manifest.get("base_url"):
        base_url = str(manifest["base_url"]).rstrip("/")
        console.print(
            f"  [green]✓[/green] Using endpoint from manifest: [bold]{base_url}[/bold]"
        )
        save_config(base_url=base_url, scope=scope)
    elif prev_base:
        base_url = prev_base
        console.print(
            f"  [green]✓[/green] Using existing endpoint: [bold]{base_url}[/bold]"
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
            base_url = "https://api.stash.ac"
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
        _reserve_bottom_padding(4)
        try:
            api_key, username = _browser_auth_flow(base_url)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled.[/yellow]")
            raise typer.Exit(1)
        save_config(api_key=api_key, username=username)
        console.print(f"  [green]✓[/green] Logged in as [bold]{username}[/bold]")

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
            existing_ws = None
            if workspace_id:
                existing_ws = next(
                    (ws for ws in my_workspaces if str(ws["id"]) == workspace_id), None
                )

            if existing_ws:
                # Preserve the previously configured workspace on re-runs.
                console.print(
                    f"  [green]✓[/green] Using existing workspace: [bold]{existing_ws['name']}[/bold]"
                )
            else:
                if my_workspaces:
                    console.print("\n  Your workspaces:")
                    for ws in my_workspaces[:5]:
                        console.print(f"    [dim]{str(ws['id'])[:8]}…[/dim]  {ws['name']}")

                default_ws = my_workspaces[0] if my_workspaces else None
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
                        save_config(default_workspace=str(matched["id"]), scope=scope)
                        console.print(
                            f"  [green]✓[/green] Using workspace [bold]{matched['name']}[/bold]"
                        )
                    else:
                        try:
                            ws_data = c.create_workspace(ws_name)
                            save_config(default_workspace=str(ws_data["id"]), scope=scope)
                            console.print(
                                f"  [green]✓[/green] Created workspace [bold]{ws_data['name']}[/bold]  invite: {ws_data['invite_code']}"
                            )
                        except StashError as e:
                            console.print(f"[red]Could not create workspace: {e.detail}[/red]")

    # --- Step 4: Coding-agent plugin ---
    # Detect coding agents on PATH and prompt per-agent for the ones that
    # don't already have the stash plugin installed. Agents that do have it
    # get a single confirmation line so re-runs don't nag.
    detected = _detected_agents()
    if detected:
        agent_label = {
            "claude": "Claude Code",
            "cursor": "Cursor",
            "codex": "Codex",
            "opencode": "opencode",
        }
        missing = [a for a in detected if not _plugin_installed(a)]
        already = [a for a in detected if a not in missing]
        if already:
            console.print(
                f"  [green]✓[/green] Stash plugin already installed for "
                f"[bold]{', '.join(agent_label[a] for a in already)}[/bold]"
            )
        for agent in missing:
            _reserve_bottom_padding(4)
            install_plugin = questionary.confirm(
                f"Detected {agent_label[agent]} on this machine. Install the stash plugin?\n"
                "  (Streams every session here to your shared history.)",
                default=True,
            ).ask()
            if not install_plugin:
                continue
            try:
                status_, detail = _INSTALLERS[agent](False)
            except Exception as e:
                status_, detail = ("failed", f"{type(e).__name__}: {e}")
            color = {"installed": "green", "skipped": "yellow", "failed": "red"}[status_]
            console.print(
                f"  [{color}]{status_:9}[/{color}] {agent:8} {detail}"
            )

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

    # Pin the config to the manifest's directory. find_project_config() walks up
    # and could resolve to a parent repo's .stash/config.json in nested setups,
    # which would enable/disable the wrong repo.
    project_path = manifest_path.parent / PROJECT_FILENAME
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

    # See enable_cmd: pin to manifest dir so we don't disable a parent repo.
    project_path = manifest_path.parent / PROJECT_FILENAME
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

# Matches the orange octopus on stash.ac — round body, two eyes, five tentacles.
STASH_OCTOPUS = r'''
              .-~~~~~~-.
             /  o    o  \
             '.________.'
              / / | \ \ \
             ( ( (|)  ) )
'''


def _pushed_scope_phrase() -> str:
    """Human phrase for 'what gets pushed', varying by the user's scope choice
    at setup. `repo` (default) pushes only from the install repo; `workspace`
    and `all` both push from anywhere on this machine."""
    scope = (_read_central_config().get("scope") or "repo").strip().lower()
    if scope == "repo":
        return "Coding agent transcripts from this repo."
    return "All coding agent transcripts from this machine."


def _current_invite() -> tuple[str, str]:
    """Return (invite_code, workspace_name) for the current default workspace,
    or ("", "") if unavailable. Best-effort — any auth/network failure falls
    back to the generic `stash workspaces info` guidance."""
    ws_id = load_config().get("default_workspace") or ""
    if not ws_id:
        return "", ""
    try:
        with _client() as c:
            data = c.get_workspace(ws_id)
    except Exception:
        return "", ""
    return str(data.get("invite_code") or ""), str(data.get("name") or "")


def _invite_url(invite_code: str) -> str:
    """Build the user-facing join URL for an invite code, mirroring the
    frontend-host logic used for login (see `stash connect` managed flow):
    managed backend → stash.ac; localhost backend → :3457; any other
    self-host → whatever the configured base_url is."""
    base_url = (load_config().get("base_url") or "").rstrip("/")
    managed_hosts = ("https://stash.ac", "https://www.stash.ac", "https://api.stash.ac")
    if base_url in managed_hosts:
        frontend = "https://stash.ac"
    elif "localhost" in base_url or "127.0.0.1" in base_url:
        frontend = base_url.replace(":3456", ":3457")
    else:
        frontend = base_url
    return f"{frontend}/join/{invite_code}"


def _workspace_url(ws_id: str) -> str:
    """Build the user-facing URL for a workspace's page on the configured
    frontend. Managed backend → app.stash.ac (the marketing site at stash.ac
    has no /workspaces redirect); localhost backend → :3457; any other
    self-host → whatever the configured base_url is."""
    base_url = (load_config().get("base_url") or "").rstrip("/")
    if "localhost" in base_url or "127.0.0.1" in base_url:
        frontend = base_url.replace(":3456", ":3457")
    elif base_url == "https://api.stash.ac":
        frontend = "https://app.stash.ac"
    else:
        frontend = base_url
    return f"{frontend}/workspaces/{ws_id}"


def _current_workspace_url() -> str:
    """Return the link to the user's default workspace, or "" if none configured."""
    ws_id = load_config().get("default_workspace") or ""
    return _workspace_url(ws_id) if ws_id else ""


def _welcome_markdown() -> str:
    invite_code, ws_name = _current_invite()
    if invite_code:
        ws_suffix = f" (workspace: {ws_name})" if ws_name else ""
        share_answer = (
            f"Send this link: {_invite_url(invite_code)} — "
        )
    else:
        share_answer = (
            "Share the invite code (`stash workspaces info <id>` prints it). "
            "Teammates run `stash connect` if needed, then "
            "`stash workspaces join <invite_code>`."
        )
    ws_url = _current_workspace_url()
    workspace_link_section = (
        f"## See your workspace\n\n"
        f"Open it in the browser to browse transcripts and activity: {ws_url}\n\n"
        if ws_url
        else ""
    )
    return f"""# You're all set up.

## What just happened

Your coding agent now has the `stash` CLI on its PATH. It can read the transcripts your teammates' coding agents push to this workspace — so it knows what the rest of your team is working on.

{workspace_link_section}## Examples of questions your agent might want answered

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
**A:** {_pushed_scope_phrase()}

**Q:** How do I do settings?
**A:** `stash sessings`

**Q:** How do I share my workspace with my team?
**A:** {share_answer}
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


def _install_claude_plugin() -> bool:
    """Install the stash plugin for Claude Code via the official marketplace.

    Both subcommands are idempotent — re-running prints a "already added /
    installed" notice rather than failing — so we don't pre-check state.
    Returns True on success, False if either subprocess call errors (errors
    are surfaced to the user inline).
    """
    import subprocess as _sp

    for cmd in (
        ["claude", "plugin", "marketplace", "add", "Fergana-Labs/stash"],
        ["claude", "plugin", "install", "stash@stash-plugins"],
    ):
        try:
            result = _sp.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        except _sp.CalledProcessError as e:
            console.print(
                f"  [yellow]`{' '.join(cmd)}` exited {e.returncode}.[/yellow]"
            )
            if e.stderr:
                console.print(f"  [dim]{e.stderr.strip().splitlines()[-1]}[/dim]")
            return False
        except (FileNotFoundError, _sp.TimeoutExpired) as e:
            console.print(f"  [yellow]Could not run `{' '.join(cmd)}`: {e}[/yellow]")
            return False
        # Surface the success line (last line of stdout, e.g. "Successfully
        # installed plugin: stash@stash-plugins (scope: user)") so the user
        # sees what happened.
        last = (result.stdout or "").strip().splitlines()
        if last:
            console.print(f"  [green]✓[/green] {last[-1]}")
    return True


def _show_setup_complete_splash(
    workspace_name: str = "",
    joined_via_invite: bool = False,
    joined_via_manifest: bool = False,
) -> None:
    """Clear the onboarding transcript and show a clean success splash."""
    _capture_install_repo()
    console.clear()
    octopus = textwrap.dedent(STASH_OCTOPUS.strip("\n"))
    logo = textwrap.dedent(STASH_LOGO.strip("\n"))
    console.print(Align.center(Text.from_markup(f"[bold #F97316]{octopus}[/bold #F97316]")))
    console.print()
    console.print(Align.center(Text.from_markup(f"[bold #1e3a8a]{logo}[/bold #1e3a8a]")))
    if (joined_via_invite or joined_via_manifest) and workspace_name:
        console.print(f"  [bold green]You joined[/bold green] [bold]{workspace_name}[/bold].\n")
    else:
        console.print("  [bold green]You're all set up.[/bold green]\n")

    invite_code, ws_name = _current_invite()
    if invite_code:
        ws_suffix = f" (workspace [bold]{ws_name}[/bold])" if ws_name else ""
        share_answer = (
            f"Send teammates this link{ws_suffix}:\n"
            f"[bold #1e3a8a]{_invite_url(invite_code)}[/bold #1e3a8a]\n"
            "They'll sign in and be joined automatically."
        )
    else:
        share_answer = (
            "Share the invite code ([#1e3a8a]stash workspaces info <id>[/#1e3a8a] prints it). "
            "Teammates run [#1e3a8a]stash connect[/#1e3a8a] if needed, then "
            "[#1e3a8a]stash workspaces join <invite_code>[/#1e3a8a]."
        )

    ws_url = _current_workspace_url()
    workspace_link_section = (
        "[bold]See your workspace[/bold]   [dim](transcripts and team activity)[/dim]\n"
        f"  [link={ws_url}][bold #1e3a8a]{ws_url}[/bold #1e3a8a][/link]\n"
        "\n"
        if ws_url
        else ""
    )
    intro = (
        "[bold]What just happened[/bold]\n"
        "Your coding agent now has the [bold #1e3a8a]stash[/bold #1e3a8a] CLI on its PATH.\n"
        "It can read the transcripts your teammates' coding agents push to this\n"
        "workspace — so it knows what the rest of your team is working on.\n"
        "\n"
        f"{workspace_link_section}"
        "[bold]Examples of questions your agent might want answered[/bold]\n"
        '  [dim]"Why did Sam bump the rate limit from 100 to 500?"[/dim]\n'
        '  [dim]"Has anyone already tried fixing the memory leak in our backend?"[/dim]\n'
        '  [dim]"Is anyone else currently working on our api gateway"[/dim]\n'
        "\n"
        "  You can read a blog post about it here: "
        "[link=https://henrydowling.com/agent-velocity.html]Agent velocity for coding teams[/link]\n"
        "\n"
        "[bold]Commands your agent can now use[/bold]\n"
        '  [#1e3a8a]stash history search "<query>"[/#1e3a8a]   full-text search across transcripts\n'
        "  [#1e3a8a]stash history query --agent <name>[/#1e3a8a]   pull a specific agent's events\n"
        "\n"
        "Run [bold]stash --help[/bold] to see everything.\n"
        "\n"
        "[bold]Q&A[/bold]"
    )

    qa_pairs = [
        (
            "Do you inject anything into my coding agent's context automatically?",
            "No.",
        ),
        (
            "What gets pushed to the shared store?",
            _pushed_scope_phrase(),
        ),
        (
            "How do I change scope or see a transcript?",
            "[#1e3a8a]stash config scope <repo|workspace|all>[/#1e3a8a]  (default: repo)\n"
            "[#1e3a8a]stash history transcript <session_id>[/#1e3a8a]  view a full transcript\n"
            '[#1e3a8a]stash history search "<query>"[/#1e3a8a]         search event content',
        ),
        (
            "How do I share my workspace with my team?",
            share_answer,
        ),
    ]

    qa_table = Table(
        show_header=False,
        show_edge=False,
        box=None,
        pad_edge=False,
        padding=(0, 1),
    )
    qa_table.add_column(style="bold", no_wrap=True)
    qa_table.add_column(overflow="fold")
    for i, (question, answer) in enumerate(qa_pairs):
        if i > 0:
            qa_table.add_row("", "")
        qa_table.add_row("Q", question)
        qa_table.add_row("A", answer)

    console.print(
        Panel(
            Group(Text.from_markup(intro), qa_table),
            title="[bold #1e3a8a]Your team's shared agent memory[/bold #1e3a8a]",
            border_style="#1e3a8a",
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


SCOPE_CHOICES = [
    ("repo", "only sessions in the install repo"),
    ("workspace", "any session tagged with this workspace"),
    ("all", "every session on this machine"),
]

OUTPUT_FORMAT_CHOICES = [
    ("human", "colored, human-readable"),
    ("json", "machine-readable JSON"),
]


def _render_settings_header(cfg: dict, central: dict) -> None:
    """Print the read-only portion of the settings page."""
    console.clear()
    console.print("[bold]Stash settings[/bold]\n")

    manifest = load_manifest()
    workspace_id = cfg.get("default_workspace") or ""
    if manifest and manifest.get("workspace_id") == workspace_id and manifest.get("workspace_name"):
        workspace_label = f"{manifest['workspace_name']}  ({workspace_id[:8]}…)"
    elif workspace_id:
        workspace_label = workspace_id
    else:
        workspace_label = "(none)"

    def row(label: str, value: str, *, highlight: bool = True) -> None:
        console.print(f"  [dim]{label}[/dim]{value}", highlight=highlight)

    row(f"{'User:':<14}", cfg.get("username") or "(not logged in)")
    # Workspace UUID would otherwise auto-highlight yellow — force neutral.
    row(f"{'Workspace:':<14}", workspace_label, highlight=False)
    row(f"{'Store:':<14}", cfg.get("default_store") or "(none)")

    last_curate_at = central.get("last_curate_at")
    if last_curate_at:
        import datetime as _dt

        ts = _dt.datetime.fromtimestamp(float(last_curate_at)).isoformat(timespec="seconds")
        row(f"{'Last curate:':<14}", ts)
    else:
        row(f"{'Last curate:':<14}", "(never)")

    plugins_seen = [name for name, d in PLUGIN_DATA_DIRS.items() if d.exists()]
    row(f"{'Plugins:':<14}", ", ".join(plugins_seen) or "(none detected)")

    install_repo = central.get("install_repo_common_dir") or ""
    if install_repo:
        row(f"{'Install repo:':<14}", install_repo)
    console.print()


@app.command("settings")
def settings_cmd(as_json: bool = typer.Option(False, "--json")):
    """Interactive settings page. Pass --json for a read-only snapshot."""
    cfg = load_config()
    central = _read_central_config()

    display_cfg = dict(cfg)
    if display_cfg.get("api_key"):
        display_cfg["api_key"] = display_cfg["api_key"][:10] + "..."

    if as_json or cfg.get("output_format") == "json":
        output_json(
            {
                "config": display_cfg,
                "streaming_enabled": bool(central.get("streaming_enabled", True)),
                "auto_curate": bool(central.get("auto_curate", True)),
                "last_curate_at": central.get("last_curate_at"),
                "plugins_installed": [
                    name for name, d in PLUGIN_DATA_DIRS.items() if d.exists()
                ],
                "scope": (central.get("scope") or "repo").strip().lower(),
                "install_repo_common_dir": central.get("install_repo_common_dir") or "",
            }
        )
        return

    while True:
        cfg = load_config()
        central = _read_central_config()
        _render_settings_header(cfg, central)

        streaming_enabled = bool(central.get("streaming_enabled", True))
        auto_curate = bool(central.get("auto_curate", True))
        scope = (central.get("scope") or "repo").strip().lower()
        output_format = cfg.get("output_format", "human")
        base_url = cfg.get("base_url", "")

        rows = [
            ("Streaming", "on" if streaming_enabled else "off", "streaming"),
            ("Auto-curate", "on" if auto_curate else "off", "auto_curate"),
            ("Scope", scope, "scope"),
            ("Output format", output_format, "output_format"),
            ("Endpoint", base_url, "base_url"),
        ]
        label_w = max(len(label) for label, _, _ in rows)
        choices = [
            questionary.Choice(f"{label:<{label_w}}   {value}", value=key)
            for label, value, key in rows
        ]
        choices.append(questionary.Choice("Exit", value="exit"))

        picked = questionary.select(
            "Pick a setting to change (enter to edit, q to exit)",
            choices=choices,
            use_shortcuts=True,
        ).ask()

        if picked in (None, "exit"):
            return

        if picked == "streaming":
            _write_central_config({"streaming_enabled": not streaming_enabled})
        elif picked == "auto_curate":
            _write_central_config({"auto_curate": not auto_curate})
        elif picked == "scope":
            label_w2 = max(len(v) for v, _ in SCOPE_CHOICES)
            scope_choices = [
                questionary.Choice(f"{v:<{label_w2}}   {desc}", value=v)
                for v, desc in SCOPE_CHOICES
            ]
            new_scope = questionary.select(
                "Upload scope — which sessions push to the shared store?",
                choices=scope_choices,
                default=next((ch for ch in scope_choices if ch.value == scope), None),
                use_shortcuts=True,
            ).ask()
            if new_scope:
                _write_central_config({"scope": new_scope})
        elif picked == "output_format":
            label_w2 = max(len(v) for v, _ in OUTPUT_FORMAT_CHOICES)
            fmt_choices = [
                questionary.Choice(f"{v:<{label_w2}}   {desc}", value=v)
                for v, desc in OUTPUT_FORMAT_CHOICES
            ]
            new_fmt = questionary.select(
                "Output format for CLI commands",
                choices=fmt_choices,
                default=next((ch for ch in fmt_choices if ch.value == output_format), None),
                use_shortcuts=True,
            ).ask()
            if new_fmt:
                save_config(output_format=new_fmt)
        elif picked == "base_url":
            new_url = questionary.text("Endpoint base URL", default=base_url).ask()
            if new_url:
                save_config(base_url=new_url.strip().rstrip("/"))


keys_app = typer.Typer(help="Manage your API keys across devices.")
app.add_typer(keys_app, name="keys")


@keys_app.command("list")
def keys_list(as_json: bool = typer.Option(False, "--json")):
    """List your active API keys (one per device / login)."""
    with _client() as c:
        try:
            keys = c.list_api_keys()
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(keys)
        return
    if not keys:
        console.print("[dim]No active API keys.[/dim]")
        return
    for k in keys:
        last = k.get("last_used_at") or "never"
        console.print(
            f"  [bold]{k['name']}[/bold]  "
            f"[dim]id: {k['id']}  created: {str(k['created_at'])[:10]}  "
            f"last used: {str(last)[:10]}[/dim]"
        )


@keys_app.command("revoke")
def keys_revoke(key_id: str = typer.Argument(..., help="Key id to revoke.")):
    """Revoke an API key by id. Any device using it will 401 on next call."""
    with _client() as c:
        try:
            c.revoke_api_key(key_id)
        except StashError as e:
            _err(e)
    console.print(f"[green]Revoked key {key_id}.[/green]")


@app.command("disconnect")
def disconnect(as_json: bool = typer.Option(False, "--json")):
    """Sign out and clear stash config so the next `stash connect` re-onboards.

    Deletes the user and project config files (auth, workspace, endpoint).
    Plugin hooks stay installed but go inert with no api_key to push to.
    """
    from .config import clear_config

    json_mode = as_json or load_config().get("output_format") == "json"
    clear_config("user")
    clear_config("project")
    if json_mode:
        output_json({"disconnected": True})
        return
    console.print("[yellow]Disconnected.[/yellow] Cleared auth, workspace, and endpoint.")
    console.print("  Run [bold]stash connect[/bold] to set up again.")


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
