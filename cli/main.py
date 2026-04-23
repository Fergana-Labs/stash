"""Stash CLI — command-line interface for workspaces, notebooks, tables, history, and search."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import questionary
import typer
from rich.align import Align
from rich.panel import Panel
from rich.text import Text

from .client import StashClient, StashError
from .config import (
    MANIFEST_FILE,
    PRODUCTION_BASE_URL,
    Manifest,
    clear_streaming,
    load_config,
    load_enabled_agents,
    load_manifest,
    save_config,
    save_enabled_agents,
    set_streaming,
    stored_base_url,
)
from .formatting import console, output_json, print_members, print_rooms, print_user

app = typer.Typer(name="stash", help="Stash CLI — workspaces, notebooks, tables, history.")


def _client() -> StashClient:
    cfg = load_config()
    return StashClient(base_url=cfg["base_url"], api_key=cfg.get("api_key", ""))


def _use_json(flag: bool) -> bool:
    return flag


def _resolve_workspace() -> str:
    manifest = load_manifest()
    if manifest and manifest.get("workspace_id"):
        return manifest["workspace_id"]

    with _client() as c:
        mine = c.list_workspaces(mine=True)
    if not mine:
        console.print("[red]No workspaces found. Run [bold]stash connect[/bold] first.[/red]")
        raise typer.Exit(1)
    if len(mine) == 1:
        return str(mine[0]["id"])

    choice = questionary.select(
        "Which workspace?",
        choices=[questionary.Choice(w.get("name", str(w["id"])), value=str(w["id"])) for w in mine],
    ).ask()
    if choice is None:
        raise typer.Exit(1)
    return choice


def _err(e: StashError) -> None:
    if isinstance(e.detail, list):
        console.print(f"[red]Error [{e.status_code}]:[/red]")
        for item in e.detail:
            console.print(f"  [red]• {item}[/red]")
    else:
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
    if api in ("https://api.joinstash.ai",):
        return "https://joinstash.ai/connect-token"
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
            r = c.post("/api/v1/users/cli-auth/sessions", json={"device_name": device_name})
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
        "https://api.joinstash.ai",
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


def _agent_present(agent: str) -> bool:
    """True if the agent is usable on this machine (binary on PATH or config dir exists)."""
    import shutil

    if shutil.which(_AGENT_BINARY[agent]):
        return True
    if agent == "cursor":
        return (Path.home() / ".cursor").is_dir()
    return False


def _detected_agents() -> list[str]:
    return [a for a in _SUPPORTED_AGENTS if _agent_present(a)]


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

    Stash-owned entries are identified by the shared `stashai/plugin/assets/<agent>`
    suffix embedded in their command strings — so re-runs sweep out every
    stash-owned entry (including stale ones left by old dev checkouts or prior
    pipx versions) and leave user-added entries untouched. Returns 'installed',
    'skipped', or 'failed'.
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

    stash_marker = f"stashai/plugin/assets/{plugin_root.name}"
    tmpl_hooks = tmpl_data.get("hooks", {})
    existing_hooks = existing.setdefault("hooks", {})
    changed = False
    for event, tmpl_entries in tmpl_hooks.items():
        if not isinstance(tmpl_entries, list):
            continue
        cur = existing_hooks.get(event) or []
        if not isinstance(cur, list):
            cur = []
        user_entries = [e for e in cur if not _entry_references(e, stash_marker)]
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


def _drop_cursor_project_rule(repo_root: Path) -> Path | None:
    """Drop a stash.mdc into <repo>/.cursor/rules/ so Cursor agents in this
    repo know the stash CLI is available. Cursor only auto-loads .mdc rules
    from project-level .cursor/rules/ — there's no global file location.
    Returns the destination path on success, None if cursor isn't detected.
    """
    if not _agent_present("cursor"):
        return None

    from stashai.plugin.assets import assets_dir

    src = assets_dir("cursor") / "stash.mdc"
    if not src.exists():
        return None

    dest = repo_root / ".cursor" / "rules" / "stash.mdc"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text())
    return dest


_CODEX_MARKER = "# stash-plugin"
_AGENTS_MD_BEGIN = "<!-- stash-plugin:begin -->"
_AGENTS_MD_END = "<!-- stash-plugin:end -->"


def _upsert_agents_md(path: Path, body: str) -> None:
    """Idempotently write a stash-owned block into an AGENTS.md-style file."""
    block = f"{_AGENTS_MD_BEGIN}\n{body.rstrip()}\n{_AGENTS_MD_END}"
    existing = path.read_text() if path.exists() else ""

    if _AGENTS_MD_BEGIN in existing and _AGENTS_MD_END in existing:
        pre, rest = existing.split(_AGENTS_MD_BEGIN, 1)
        _, post = rest.split(_AGENTS_MD_END, 1)
        new = f"{pre}{block}{post}"
    else:
        sep = "" if not existing or existing.endswith("\n") else "\n"
        new = f"{existing}{sep}{block}\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new)


def _ask_codex_network_access() -> bool:
    """Prompt the user to enable top-level `network_access` for codex's
    workspace-write sandbox."""
    console.print(
        "For stash to work on codex specifically, we need to let bash ",
        "commands make network requests so that we can upload chat ",
        "transcripts to the remote server.",
    )
    answer = questionary.confirm(
        "Allow codex bash commands to make outbound network requests?",
        default=True,
    ).ask()
    return True if answer is None else bool(answer)


def _strip_top_level_sandbox(snippet: str) -> str:
    """Call this when the user opts not to grant outbound network
    request access. It removes the toml that grants codex outbound
    network request access."""
    start = snippet.find("[sandbox_workspace_write]")
    if start == -1:
        return snippet
    prev_blank = snippet.rfind("\n\n", 0, start)
    block_start = prev_blank + 2 if prev_blank != -1 else start
    end = snippet.find("[profiles.stash]", start)
    if end == -1:
        return snippet[:block_start].rstrip() + "\n"
    prev_blank_end = snippet.rfind("\n\n", start, end)
    block_end = prev_blank_end + 2 if prev_blank_end != -1 else end
    return snippet[:block_start] + snippet[block_end:]


def _install_codex(force: bool) -> tuple[str, str]:
    from stashai.plugin.assets import assets_dir

    root = assets_dir("codex")
    hooks_dest = Path.home() / ".codex" / "hooks.json"
    template = (root / "hooks.json").read_text()
    status_ = _merge_json_hooks(hooks_dest, template, root)

    # Append config.toml snippet idempotently via marker line.
    from string import Template

    cfg_path = Path.home() / ".codex" / "config.toml"
    existing = cfg_path.read_text() if cfg_path.exists() else ""
    snippet = Template((root / "config.toml.snippet").read_text()).safe_substitute(
        PLUGIN_ROOT=str(root)
    )

    if _CODEX_MARKER not in existing:
        if not _ask_codex_network_access():
            snippet = _strip_top_level_sandbox(snippet)

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if _CODEX_MARKER not in existing:
        with cfg_path.open("a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"\n{_CODEX_MARKER}\n{snippet}\n")

    agents_src = root / "AGENTS.md"
    agents_dest = Path.home() / ".codex" / "AGENTS.md"
    if agents_src.exists():
        _upsert_agents_md(agents_dest, agents_src.read_text())

    return (status_, f"{hooks_dest} + merged {cfg_path} + {agents_dest}")


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
    already = plugin_path in plugins
    plugins = [p for p in plugins if p != plugin_path]
    plugins.append(plugin_path)
    cfg["plugin"] = plugins
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")

    agents_src = root / "AGENTS.md"
    agents_dest = cfg_path.parent / "AGENTS.md"
    if agents_src.exists():
        _upsert_agents_md(agents_dest, agents_src.read_text())

    if already and not force:
        return ("skipped", f"{cfg_path} already references plugin.ts + {agents_dest}")
    return ("installed", f"{cfg_path} (plugin entry added) + {agents_dest}")


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
    ws = workspace_id or _resolve_workspace()
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
    ws = workspace_id or _resolve_workspace()
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
    ws = workspace_id or _resolve_workspace()
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
                else c.list_notebooks(workspace_id or _resolve_workspace())
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a notebook collection."""
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
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


def _markdown_snippet(file_resp: dict) -> str:
    """Build an image or link markdown snippet from an uploaded FileResponse."""
    name = file_resp["name"]
    url = file_resp["url"]
    ct = file_resp.get("content_type", "") or ""
    if ct.startswith("image/"):
        return f"![{name}]({url})"
    return f"[{name}]({url})"


def _prepend_attachments(
    c: StashClient, workspace_id: str, content: str, attach: list[str] | None
) -> str:
    if not attach:
        return content
    snippets = [_markdown_snippet(c.upload_ws_file(workspace_id, p)) for p in attach]
    block = "\n\n".join(snippets)
    return f"{block}\n\n{content}" if content else block


@nb_app.command("add-page")
def nb_add_page(
    notebook_id: str = typer.Argument(...),
    name: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    content: str = typer.Option(""),
    attach: list[str] = typer.Option(
        None, "--attach", help="Local file path to upload and embed (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Add a page to a notebook."""
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            for p in attach or []:
                if not Path(p).is_file():
                    console.print(f"[red]Not a file: {p}[/red]")
                    raise typer.Exit(1)
            body = _prepend_attachments(c, ws, content, attach)
            data = c.create_page(ws, notebook_id, name, content=body)
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
            ws = workspace_id or _resolve_workspace()
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
    attach: list[str] = typer.Option(
        None, "--attach", help="Local file path to upload and prepend (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Update a page. Reads from stdin if --content not given."""
    if content is None and not sys.stdin.isatty():
        content = sys.stdin.read()
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            for p in attach or []:
                if not Path(p).is_file():
                    console.print(f"[red]Not a file: {p}[/red]")
                    raise typer.Exit(1)
            if attach:
                base = (
                    content
                    if content is not None
                    else c.get_page(ws, notebook_id, page_id).get("content_markdown", "")
                )
                content = _prepend_attachments(c, ws, base, attach)
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
    ws = workspace_id or _resolve_workspace()
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
    attach: list[str] = typer.Option(
        None, "--attach", help="Local file path to upload and attach (repeatable)."
    ),
    attach_id: list[str] = typer.Option(
        None, "--attach-id", help="Pre-uploaded file id to attach (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Push an event to the workspace history."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            attachments: list[dict] = []
            for path in attach or []:
                f = _upload_path(c, ws, path)
                attachments.append(
                    {"file_id": f["id"], "name": f["name"], "content_type": f["content_type"]}
                )
            for fid in attach_id or []:
                f = _get_file_meta(c, ws, fid)
                attachments.append(
                    {"file_id": f["id"], "name": f["name"], "content_type": f["content_type"]}
                )
            data = c.push_event(
                ws,
                agent_name=agent_name,
                event_type=event_type,
                content=content,
                session_id=session_id,
                tool_name=tool_name,
                attachments=attachments or None,
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
                ws = workspace_id or _resolve_workspace()
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
    ws = workspace_id or _resolve_workspace()
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

    ws = workspace_id or _resolve_workspace()
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
    """Translate column names to IDs in a data dict. Raises on unknown keys."""
    cols = table.get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    id_set = {col["id"] for col in cols}
    resolved = {}
    unknown = []
    for k, v in data.items():
        if k in id_set:
            resolved[k] = v
        elif k in name_to_id:
            resolved[name_to_id[k]] = v
        else:
            unknown.append(k)
    if unknown:
        valid = ", ".join(col["name"] for col in cols) or "(none)"
        raise StashError(
            422,
            [f"unknown column '{k}'. Valid columns: {valid}" for k in unknown],
        )
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
    as_json: bool = typer.Option(False, "--json"),
):
    """List tables. --all for cross-workspace."""
    with _client() as c:
        try:
            if all_:
                data = c.all_tables()
            else:
                data = c.list_tables(workspace_id or _resolve_workspace())
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a table. --columns accepts JSON array of {name, type, options?}."""
    cols = json.loads(columns) if columns else []
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
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


def _parse_uploads(upload: list[str] | None) -> dict[str, str]:
    """Parse repeated --upload col=path into {col: path}. Last one wins on collision."""
    if not upload:
        return {}
    out: dict[str, str] = {}
    for spec in upload:
        if "=" not in spec:
            console.print(f"[red]--upload expects col=path, got: {spec}[/red]")
            raise typer.Exit(1)
        col, path = spec.split("=", 1)
        col, path = col.strip(), path.strip()
        if not col or not path:
            console.print(f"[red]--upload expects col=path, got: {spec}[/red]")
            raise typer.Exit(1)
        if not Path(path).is_file():
            console.print(f"[red]Not a file: {path}[/red]")
            raise typer.Exit(1)
        out[col] = path
    return out


def _apply_uploads(
    c: StashClient, workspace_id: str, row_data: dict, uploads: dict[str, str]
) -> dict:
    """Upload each file and set the file URL as the value for the named column.
    Explicit values already in row_data for the same column take precedence."""
    for col, path in uploads.items():
        if col in row_data:
            continue
        f = c.upload_ws_file(workspace_id, path)
        row_data[col] = f["url"]
    return row_data


@tables_app.command("insert")
def tables_insert(
    table_id: str = typer.Argument(...),
    data: str = typer.Argument(..., help='JSON: {"Name":"Alice","Status":"active"}'),
    workspace_id: str = typer.Option(None, "--ws"),
    upload: list[str] = typer.Option(
        None, "--upload", help="col=path — upload file and set URL as cell (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Insert a row. Data is a JSON object with column names as keys."""
    row_data = json.loads(data)
    uploads = _parse_uploads(upload)
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            row_data = _apply_uploads(c, ws, row_data, uploads)
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
            ws = workspace_id or _resolve_workspace()
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
    upload: list[str] = typer.Option(
        None, "--upload", help="col=path — upload file and set URL as cell (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Update a row (partial merge). Data is JSON with column names as keys."""
    row_data = json.loads(data)
    uploads = _parse_uploads(upload)
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            row_data = _apply_uploads(c, ws, row_data, uploads)
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
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
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
            ws = workspace_id or _resolve_workspace()
            c.delete_table(ws, table_id)
        except StashError as e:
            _err(e)
    console.print("[green]Table deleted.[/green]")


# ===========================================================================
# Files
# ===========================================================================

files_app = typer.Typer(help="Files — upload, list, and remove workspace files.")
app.add_typer(files_app, name="files")


def _upload_path(c: StashClient, workspace_id: str, path: str) -> dict:
    """Upload `path` to the given workspace. Returns FileResponse dict."""
    if not Path(path).is_file():
        console.print(f"[red]Not a file: {path}[/red]")
        raise typer.Exit(1)
    return c.upload_ws_file(workspace_id, path)


def _get_file_meta(c: StashClient, workspace_id: str, file_id: str) -> dict:
    return c.get_ws_file(workspace_id, file_id)


@files_app.command("upload")
def files_upload(
    path: str = typer.Argument(..., help="Local file path to upload."),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Upload a file to a workspace."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = _upload_path(c, ws, path)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Uploaded[/green] {data['name']}  [dim]{data['id']}[/dim]")
        console.print(data["url"])


@files_app.command("list")
def files_list(
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List files in a workspace."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.list_ws_files(ws)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if not data:
        console.print("[dim]No files.[/dim]")
        return
    for f in data:
        size_kb = (f.get("size_bytes") or 0) / 1024
        console.print(
            f"  {f['id']}  [bold]{f['name']}[/bold]  "
            f"[dim]{f.get('content_type', '')}  {size_kb:.1f} KB[/dim]"
        )


@files_app.command("rm")
def files_rm(
    file_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Delete a file."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.delete_ws_file(ws, file_id)
        except StashError as e:
            _err(e)
    console.print("[green]File deleted.[/green]")


@files_app.command("text")
def files_text(
    file_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Print extracted text for a file (PDFs with embedded text, or plain text)."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.get_ws_file_text(ws, file_id)
        except StashError as e:
            _err(e)
    text = data.get("text") if isinstance(data, dict) else None
    status = data.get("status") if isinstance(data, dict) else None
    error = data.get("error") if isinstance(data, dict) else None
    if text:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    if status in ("pending", "processing"):
        console.print("[yellow]Extraction in progress. Try again in a moment.[/yellow]")
        raise typer.Exit(2)
    if status == "failed":
        console.print(f"[red]Extraction failed:[/red] {error or 'unknown error'}")
        raise typer.Exit(1)
    console.print("[dim]No extracted text available for this file.[/dim]")
    raise typer.Exit(1)


# ===========================================================================
# Prompts — reusable stash agent prompts, printed to stdout
# ===========================================================================

prompts_app = typer.Typer(help="Print reusable stash agent prompts.")
app.add_typer(prompts_app, name="prompts")


@prompts_app.command("curate")
def prompts_curate():
    """Print the sleep-time wiki curation prompt to stdout."""
    from stashai.plugin.sleep_prompt import SLEEP_PROMPT

    print(SLEEP_PROMPT)


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
    managed_hosts = ("https://joinstash.ai", "https://www.joinstash.ai", "https://api.joinstash.ai")
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


def _require_auth() -> dict:
    """Return loaded config if authenticated, otherwise print error and exit."""
    cfg = load_config()
    if not cfg.get("api_key"):
        console.print("[red]Not authenticated. Run `stash login` first.[/red]")
        raise typer.Exit(1)
    return cfg


def _handle_not_member(ws_id: str, client: StashClient) -> None:
    """Handle the case where .stash exists but the user isn't a member."""
    try:
        info = client.workspace_public_info(ws_id)
        ws_name = info["name"]
        member_count = info["member_count"]
    except StashError:
        ws_name = ws_id[:8] + "…"
        member_count = "?"

    console.print(
        f"\n  This repo belongs to workspace [bold]{ws_name}[/bold] "
        f"({member_count} member{'s' if member_count != 1 else ''})."
    )
    console.print("  You're not a member yet.\n")

    existing = client.get_my_join_request(ws_id)
    if existing and existing.get("status") == "pending":
        console.print(
            "  [yellow]You already have a pending request.[/yellow] "
            "The workspace owner has been notified."
        )
        return
    if existing and existing.get("status") == "approved":
        console.print(
            "  [green]✓[/green] Your request was approved! "
            "Streaming is now active."
        )
        return

    try:
        client.create_join_request(ws_id)
        console.print(
            "  [green]✓[/green] Request sent! The workspace owner will be notified by email.\n"
            "  You'll be able to stream once your request is approved."
        )
    except StashError as e:
        if e.status_code == 409:
            console.print("  [green]✓[/green] You're already a member of this workspace!")
        else:
            console.print(f"  [red]Could not send join request: {e.detail}[/red]")


def _auto_connect_repo(repo_root: Path, cfg: dict) -> None:
    """Connect a repo to a workspace, auto-creating one named after the repo directory."""
    manifest_path = repo_root / MANIFEST_FILE

    with StashClient(base_url=cfg["base_url"], api_key=cfg["api_key"]) as c:
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text())
            ws_id = manifest.get("workspace_id", "")
            try:
                c.get_workspace(ws_id)
                console.print(
                    f"  [green]✓[/green] Already connected to workspace "
                    f"[bold]{ws_id[:8]}…[/bold]"
                )
                return
            except StashError as e:
                if e.status_code in (403, 404):
                    _handle_not_member(ws_id, c)
                    return
                raise

        repo_name = repo_root.name
        my_workspaces = c.list_workspaces(mine=True)
        matched = next((ws for ws in my_workspaces if ws["name"] == repo_name), None)
        if matched:
            console.print(f"  [green]✓[/green] Using workspace [bold]{matched['name']}[/bold]")
        else:
            matched = c.create_workspace(repo_name)
            console.print(f"  [green]✓[/green] Created workspace [bold]{matched['name']}[/bold]")

    base_url = cfg.get("base_url", PRODUCTION_BASE_URL)

    manifest: Manifest = {"workspace_id": str(matched["id"])}
    if base_url != PRODUCTION_BASE_URL:
        manifest["base_url"] = base_url

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    console.print(f"  Wrote [cyan]{MANIFEST_FILE}[/cyan]")

    set_streaming(str(matched["id"]))

    _append_claude_md(repo_root)

    console.print(
        f"\n  Commit [cyan]{MANIFEST_FILE}[/cyan] and [cyan]CLAUDE.md[/cyan] and push. "
        "Teammates will start streaming automatically."
    )


def _append_claude_md(repo_root: Path) -> None:
    """Append Stash context block to CLAUDE.md in the repo."""
    claude_md = repo_root / "CLAUDE.md"
    marker = "<!-- stash-context -->"

    if claude_md.exists():
        existing = claude_md.read_text()
        if marker in existing:
            return
    else:
        existing = ""

    block = f"""
{marker}
## Stash

This repo uses [Stash](https://joinstash.ai) for shared agent history.
Your coding agent has the `stash` CLI on its PATH. Run `stash --help` to see commands.

Common reads (all support `--json`):
- `stash history search "<query>"` — full-text search across transcripts
- `stash history query --limit 20` — latest events
- `stash history agents` — who's been active
- `stash notebooks list --all` — shared notebooks
"""
    claude_md.write_text(existing.rstrip() + "\n" + block)
    console.print("  Appended Stash context to [cyan]CLAUDE.md[/cyan]")


_AGENT_LABEL = {
    "claude": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex",
    "opencode": "opencode",
}


def _install_all_hooks(agents: list[str] | None = None) -> None:
    """Install/upgrade hooks for the given agents (defaults to all detected)."""
    detected = _detected_agents()
    if not detected:
        return

    to_install = [a for a in detected if a in agents] if agents is not None else detected

    for agent in to_install:
        try:
            status_, detail = _INSTALLERS[agent](False)
        except Exception as e:
            status_, detail = ("failed", f"{type(e).__name__}: {e}")
        if status_ == "installed":
            console.print(f"  [green]✓[/green] {_AGENT_LABEL[agent]} hook installed  {detail}")
        elif status_ == "skipped":
            console.print(f"  [green]✓[/green] {_AGENT_LABEL[agent]} hook up to date")
        elif status_ == "failed":
            console.print(f"  [red]✗[/red] {_AGENT_LABEL[agent]} hook failed  {detail}")


@app.command("login")
def login_cmd(
    welcome: bool = typer.Option(
        False,
        "--welcome",
        help="Print the post-install welcome as plain markdown and exit.",
    ),
):
    """Authenticate with Stash. On first run, walks through full onboarding."""
    if welcome:
        print(_welcome_markdown())
        return

    console.print("\n[bold]Stash login[/bold]\n")

    cfg = load_config()

    # --- Step 1: API endpoint ---
    prev_base = stored_base_url()
    if prev_base:
        base_url = prev_base
        console.print(f"  [green]✓[/green] Using endpoint: [bold]{base_url}[/bold]")
    else:
        mode_options = [
            ("Managed", "hosted by Stash", "managed"),
            ("Self-host", "run on your own machine", "self"),
        ]
        mode_label_w = max(len(label) for label, _, _ in mode_options)
        _reserve_bottom_padding(8)
        mode = questionary.select(
            "Do you want to use managed Stash or self-host?",
            choices=[
                questionary.Choice(f"{label:<{mode_label_w}}   ({desc})", value=value)
                for label, desc, value in mode_options
            ],
            use_shortcuts=True,
        ).ask()
        if mode is None:
            raise typer.Exit(1)

        if mode == "managed":
            base_url = PRODUCTION_BASE_URL
        else:
            base_url = _self_host_walkthrough(cfg)
        save_config(base_url=base_url)

    # --- Step 2: Auth ---
    has_key = bool(cfg.get("api_key"))
    if has_key:
        try:
            with StashClient(base_url=base_url, api_key=cfg["api_key"]) as c:
                user = c.whoami()
            console.print(f"  [green]✓[/green] Authenticated as [bold]{user['name']}[/bold]")
        except StashError:
            has_key = False

    if not has_key:
        _reserve_bottom_padding(4)
        try:
            api_key, username = _browser_auth_flow(base_url)
        except KeyboardInterrupt:
            console.print("\n[yellow]Authentication cancelled.[/yellow]")
            raise typer.Exit(1)
        save_config(api_key=api_key, username=username)
        console.print(f"  [green]✓[/green] Logged in as [bold]{username}[/bold]")

    cfg = load_config()

    # Returning user — just re-auth, no wizard
    if has_key:
        console.print("\n  Run [cyan]stash settings[/cyan] to change agents or endpoint.")
        return

    # --- Step 3: Upload or just read? ---
    _reserve_bottom_padding(6)
    usage_mode = questionary.select(
        "Do you want to upload transcripts, or just read?",
        choices=[
            questionary.Choice("Upload transcripts", value="upload"),
            questionary.Choice("Just read", value="read"),
        ],
        use_shortcuts=True,
    ).ask()
    if usage_mode is None:
        raise typer.Exit(1)

    if usage_mode == "read":
        _show_setup_complete_splash()
        return

    # --- Step 4: Agent detection + hook installation ---
    detected = _detected_agents()
    if detected:
        enabled = load_enabled_agents()
        default_enabled = enabled if enabled is not None else detected

        _reserve_bottom_padding(len(detected) + 4)
        selected = questionary.checkbox(
            "What coding agents do you want Stash to work on?",
            choices=[
                questionary.Choice(
                    _AGENT_LABEL.get(a, a),
                    value=a,
                    checked=a in default_enabled,
                )
                for a in detected
            ],
        ).ask()
        if selected is None:
            raise typer.Exit(1)

        save_enabled_agents(selected)
        _install_all_hooks(selected)
    else:
        save_enabled_agents([])

    # --- Step 5: Which repo? ---
    repo_root = _git_toplevel()
    repo_name = repo_root.name if repo_root else None

    this_repo_label = f"This repo ({repo_name})" if repo_name else "This repo"
    repo_choices = [
        questionary.Choice(this_repo_label, value="this"),
        questionary.Choice("Another repo", value="other"),
        questionary.Choice("Done", value="done"),
    ]
    _reserve_bottom_padding(6)
    answer = questionary.select(
        "Which repo do you want to upload transcripts in?",
        choices=repo_choices,
        default=repo_choices[0] if repo_root else repo_choices[2],
        use_shortcuts=True,
    ).ask()
    if answer is None:
        raise typer.Exit(1)

    if answer == "this":
        if not repo_root:
            console.print("[yellow]Not inside a git repo. Run `stash connect` from a repo.[/yellow]")
        else:
            try:
                _auto_connect_repo(repo_root, cfg)
            except StashError as e:
                console.print(f"[red]Could not connect repo: {e.detail}[/red]")
    elif answer == "other":
        _reserve_bottom_padding(4)
        repo_path = typer.prompt("Path to repo").strip()
        target = Path(repo_path).expanduser().resolve()
        target_root = _git_toplevel(target)
        if not target_root:
            console.print(f"[red]{repo_path} is not a git repo.[/red]")
        else:
            try:
                _auto_connect_repo(target_root, cfg)
            except StashError as e:
                console.print(f"[red]Could not connect repo: {e.detail}[/red]")

    _show_setup_complete_splash()


@app.command("connect")
def connect_cmd():
    """Connect this repo to a Stash workspace."""
    cfg = _require_auth()

    repo_root = _git_toplevel()
    if not repo_root:
        console.print("[red]Not inside a git repo.[/red]")
        raise typer.Exit(1)

    _auto_connect_repo(repo_root, cfg)


@app.command("join")
def join_cmd():
    """Request to join this repo's workspace."""
    cfg = _require_auth()

    repo_root = _git_toplevel()
    if not repo_root:
        console.print("[red]Not inside a git repo.[/red]")
        raise typer.Exit(1)

    manifest_path = repo_root / MANIFEST_FILE
    if not manifest_path.is_file():
        console.print("[yellow]No .stash file found. Run `stash connect` first.[/yellow]")
        raise typer.Exit(1)

    manifest = json.loads(manifest_path.read_text())
    ws_id = manifest.get("workspace_id", "")

    with StashClient(base_url=cfg["base_url"], api_key=cfg["api_key"]) as c:
        _handle_not_member(ws_id, c)


@app.command("leave")
def leave_cmd():
    """Leave this repo's workspace."""
    cfg = _require_auth()

    repo_root = _git_toplevel()
    if not repo_root:
        console.print("[red]Not inside a git repo.[/red]")
        raise typer.Exit(1)

    manifest_path = repo_root / MANIFEST_FILE
    if not manifest_path.is_file():
        console.print("[yellow]No .stash file found. Nothing to leave.[/yellow]")
        raise typer.Exit(1)

    manifest = json.loads(manifest_path.read_text())
    ws_id = manifest.get("workspace_id", "")

    with StashClient(base_url=cfg["base_url"], api_key=cfg["api_key"]) as c:
        try:
            c.leave_workspace(ws_id)
        except StashError as e:
            if "owner" in str(e.detail).lower():
                console.print("  [red]Owners cannot leave their own workspace.[/red]")
                return
            console.print(f"  [red]{e.detail}[/red]")
            return

    clear_streaming(ws_id)
    console.print(f"  [green]✓[/green] Left workspace {ws_id[:8]}…")


@app.command("start")
def start_cmd():
    """Resume streaming transcripts (undoes `stash stop`)."""
    cfg = _require_auth()

    manifest = load_manifest()
    if not manifest:
        console.print("[yellow]No .stash file found in this repo.[/yellow]")
        raise typer.Exit(1)

    workspace_id = manifest.get("workspace_id", "")
    if not workspace_id:
        console.print("[red].stash file is missing workspace_id.[/red]")
        raise typer.Exit(1)

    with StashClient(base_url=cfg["base_url"], api_key=cfg["api_key"]) as c:
        try:
            c.get_workspace(workspace_id)
        except StashError as e:
            if e.status_code in (403, 404):
                req = c.get_my_join_request(workspace_id)
                if req and req.get("status") == "approved":
                    console.print(
                        f"  [green]✓[/green] Your request to join was approved!"
                    )
                elif req and req.get("status") == "pending":
                    console.print(
                        "  [yellow]Your join request is still pending.[/yellow] "
                        "You'll be able to stream once approved."
                    )
                    return
                else:
                    console.print(
                        "  [yellow]You're not a member of this workspace.[/yellow] "
                        "Run [cyan]stash join[/cyan] to request access."
                    )
                    return
            else:
                raise

    set_streaming(workspace_id)
    console.print(f"  [green]✓[/green] Streaming enabled for workspace {workspace_id[:8]}…")


@app.command("stop")
def stop_cmd():
    """Stop streaming transcripts for this repo's workspace."""
    _require_auth()

    manifest = load_manifest()
    if not manifest:
        console.print("[yellow]No .stash file found in this repo.[/yellow]")
        raise typer.Exit(1)

    workspace_id = manifest.get("workspace_id", "")
    if not workspace_id:
        console.print("[red].stash file is missing workspace_id.[/red]")
        raise typer.Exit(1)

    clear_streaming(workspace_id)
    console.print(f"  [green]✓[/green] Streaming stopped for workspace {workspace_id[:8]}…")


# ===========================================================================
# Repo-level enablement: invoked from `stash connect`; toggled via enable/disable
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


STASH_LOGO = r"""
 ███████╗████████╗ █████╗ ███████╗██╗  ██╗
 ██╔════╝╚══██╔══╝██╔══██╗██╔════╝██║  ██║
 ███████╗   ██║   ███████║███████╗███████║
 ╚════██║   ██║   ██╔══██║╚════██║██╔══██║
 ███████║   ██║   ██║  ██║███████║██║  ██║
 ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
"""

# Matches the orange octopus on joinstash.ai — round body, two eyes, five tentacles.
STASH_OCTOPUS = r"""
              .-~~~~~~-.
             /  o    o  \
             '.________.'
              / / | \ \ \
             ( ( (|)  ) )
"""


def _frontend_base_url() -> str:
    """Return the frontend root for the currently configured backend.

    api.joinstash.ai → app.joinstash.ai, localhost backend → :3457."""
    base_url = (load_config().get("base_url") or "").rstrip("/")
    if "localhost" in base_url or "127.0.0.1" in base_url:
        return base_url.replace(":3456", ":3457")
    from urllib.parse import urlparse as _urlparse

    parsed = _urlparse(base_url)
    host = parsed.hostname or ""
    if host.startswith("api."):
        return f"{parsed.scheme}://app.{host[4:]}"
    return base_url


def _workspace_url(ws_id: str) -> str:
    """Build the user-facing URL for a workspace's page on the configured frontend."""
    return f"{_frontend_base_url()}/workspaces/{ws_id}"


def _current_workspace_url() -> str:
    """Return the link to the manifest's workspace, or "" if no manifest."""
    m = load_manifest()
    ws_id = (m.get("workspace_id") if m else None) or ""
    return _workspace_url(ws_id) if ws_id else ""


def _transcripts_url() -> str:
    """Best-effort link to where the user can see their transcripts in the web
    UI. Uses the manifest's workspace if available; falls back to the frontend
    root so we still hand the user a usable link."""
    return _current_workspace_url() or _frontend_base_url()


def _welcome_markdown() -> str:
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

## How do I share my workspace with my team?

Commit the `.stash` file and push. Teammates who clone the repo will see a prompt to run `stash start`.
"""


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
            console.print(f"  [yellow]`{' '.join(cmd)}` exited {e.returncode}.[/yellow]")
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


def _show_setup_complete_splash() -> None:
    """Show a clean success splash after first-run login."""
    console.clear()
    octopus = textwrap.dedent(STASH_OCTOPUS.strip("\n"))
    logo = textwrap.dedent(STASH_LOGO.strip("\n"))
    console.print(Align.center(Text.from_markup(f"[bold #F97316]{octopus}[/bold #F97316]")))
    console.print()
    console.print(Align.center(Text.from_markup(f"[bold #1e3a8a]{logo}[/bold #1e3a8a]")))
    console.print("  [bold green]You're all set up.[/bold green]\n")

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
        "[bold]Commands your agent can now use[/bold]\n"
        '  [#1e3a8a]stash history search "<query>"[/#1e3a8a]   full-text search across transcripts\n'
        "  [#1e3a8a]stash history query --agent <name>[/#1e3a8a]   pull a specific agent's events\n"
        "\n"
        "Run [bold]stash --help[/bold] to see everything.\n"
        "\n"
        "[bold]Share with your team[/bold]\n"
        "Commit the [cyan].stash[/cyan] file and push. Teammates who clone the repo\n"
        "will see a prompt to run [cyan]stash start[/cyan]."
    )

    console.print(
        Panel(
            Text.from_markup(intro),
            title="[bold #1e3a8a]Your team's shared agent memory[/bold #1e3a8a]",
            border_style="#1e3a8a",
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


def _render_settings_header(cfg: dict, central: dict) -> None:
    """Print the read-only portion of the settings page."""
    console.clear()
    console.print("[bold]Stash settings[/bold]\n")

    manifest = load_manifest()
    workspace_id = (manifest.get("workspace_id") if manifest else None) or ""
    workspace_label = workspace_id[:12] + "…" if workspace_id else "(none — no .stash file)"

    def row(label: str, value: str, *, highlight: bool = True) -> None:
        console.print(f"  [dim]{label}[/dim]{value}", highlight=highlight)

    row(f"{'User:':<14}", cfg.get("username") or "(not logged in)")
    row(f"{'Workspace:':<14}", workspace_label, highlight=False)
    row(f"{'Store:':<14}", cfg.get("default_store") or "(none)")

    last_curate_at = central.get("last_curate_at")
    if last_curate_at:
        import datetime as _dt

        ts = _dt.datetime.fromtimestamp(float(last_curate_at)).isoformat(timespec="seconds")
        row(f"{'Last curate:':<14}", ts)
    else:
        row(f"{'Last curate:':<14}", "(never)")

    enabled = load_enabled_agents()
    detected = _detected_agents()
    if enabled is None:
        agents_label = ", ".join(_AGENT_LABEL.get(a, a) for a in detected) or "(none detected)"
    else:
        agents_label = ", ".join(_AGENT_LABEL.get(a, a) for a in enabled) or "(none)"
    row(f"{'Streaming:':<14}", agents_label)

    plugins_seen = [name for name, d in PLUGIN_DATA_DIRS.items() if d.exists()]
    row(f"{'Plugins:':<14}", ", ".join(plugins_seen) or "(none detected)")
    console.print()


@app.command("settings")
def settings_cmd(as_json: bool = typer.Option(False, "--json")):
    """Interactive settings page. Pass --json for a read-only snapshot."""
    cfg = load_config()
    central = _read_central_config()

    display_cfg = dict(cfg)
    if display_cfg.get("api_key"):
        display_cfg["api_key"] = display_cfg["api_key"][:10] + "..."

    if as_json:
        output_json(
            {
                "config": display_cfg,
                "auto_curate": bool(central.get("auto_curate", True)),
                "last_curate_at": central.get("last_curate_at"),
                "enabled_agents": load_enabled_agents(),
                "plugins_installed": [name for name, d in PLUGIN_DATA_DIRS.items() if d.exists()],
            }
        )
        return

    while True:
        cfg = load_config()
        central = _read_central_config()
        _render_settings_header(cfg, central)

        auto_curate = bool(central.get("auto_curate", True))
        base_url = cfg.get("base_url", "")
        enabled = load_enabled_agents()
        detected = _detected_agents()
        enabled_label = ", ".join(_AGENT_LABEL.get(a, a) for a in (enabled or detected)) or "(none)"

        rows = [
            ("Streaming", enabled_label, "enabled_agents"),
            ("Auto-curate", "on" if auto_curate else "off", "auto_curate"),
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

        if picked == "enabled_agents":
            current_enabled = enabled if enabled is not None else detected
            selected = questionary.checkbox(
                "Which coding agents should stream to Stash?",
                choices=[
                    questionary.Choice(
                        _AGENT_LABEL.get(a, a),
                        value=a,
                        checked=a in current_enabled,
                    )
                    for a in detected
                ],
            ).ask()
            if selected is not None:
                save_enabled_agents(selected)
                _install_all_hooks(selected)
        elif picked == "auto_curate":
            _write_central_config({"auto_curate": not auto_curate})
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


@app.command("logout")
def logout_cmd(as_json: bool = typer.Option(False, "--json")):
    """Sign out and clear credentials. Hooks go inert until you `stash login` again."""
    from .config import clear_config

    json_mode = as_json
    clear_config()
    if json_mode:
        output_json({"logged_out": True})
        return
    console.print("[yellow]Logged out.[/yellow] Cleared auth and preferences.")
    console.print("  Run [bold]stash login[/bold] to sign in again.")


@app.command("disconnect")
def disconnect_cmd():
    """Disconnect this repo from Stash. Removes the .stash file."""
    repo_root = _git_toplevel()
    if not repo_root:
        console.print("[red]Not inside a git repo.[/red]")
        raise typer.Exit(1)

    manifest_path = repo_root / MANIFEST_FILE
    if not manifest_path.is_file():
        console.print("[yellow]No .stash file found — this repo isn't connected.[/yellow]")
        return

    manifest = load_manifest()
    workspace_id = (manifest.get("workspace_id") or "") if manifest else ""
    manifest_path.unlink()
    if workspace_id:
        clear_streaming(workspace_id)
    console.print(f"  [green]✓[/green] Removed [cyan]{MANIFEST_FILE}[/cyan] — repo disconnected.")


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
):
    """Show or set config. Keys: base_url.

    Writes to ~/.stash/config.json.
    """
    from .config import USER_CONFIG_FILE

    if key and value:
        allowed = {"base_url", "api_key", "username"}
        if key not in allowed:
            console.print(f"[red]Unknown config key: {key}[/red]")
            raise typer.Exit(1)
        save_config(**{key: value})
        console.print(f"[green]{key} = {value}[/green]")
        return

    cfg = load_config()
    display = dict(cfg)
    if display.get("api_key"):
        display["api_key"] = display["api_key"][:10] + "..."

    console.print(f"[dim]config:  {USER_CONFIG_FILE}[/dim]\n")
    console.print(json.dumps(display, indent=2, default=str))


if __name__ == "__main__":
    app()
