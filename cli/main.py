"""Stash CLI — command-line interface for workspaces, files, tables, sessions, and search."""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

import questionary
import typer
from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from stashai.plugin.doctor import shadow_install_warning
from stashai.plugin.upload_status import read_upload_status

from . import __version__, telemetry
from .client import CartridgeClient, CartridgeError, stash_permissions_for_access
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
    write_manifest,
)
from .formatting import console, output_json, print_members, print_user, print_workspaces

app = typer.Typer(
    name="stash",
    help="Stash CLI — workspaces, Cartridges, files, tables, and sessions.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"stash {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        is_eager=True,
        callback=_version_callback,
        help="Print the installed stash CLI version and exit.",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    typer.echo(ctx.get_help())
    raise typer.Exit()


@app.command()
def upgrade() -> None:
    """Upgrade the stash CLI to the latest version on PyPI."""
    import shutil
    import subprocess

    if not shutil.which("uv"):
        typer.echo(
            "uv is not on PATH. Re-run the installer: "
            'bash -c "$(curl -fsSL https://joinstash.ai/install)"',
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(f"Upgrading stashai from {__version__}…")
    result = subprocess.run(
        ["uv", "tool", "install", "--force", "--reinstall", "--refresh", "stashai"]
    )
    raise typer.Exit(result.returncode)


def _client() -> CartridgeClient:
    cfg = load_config()
    return CartridgeClient(base_url=cfg["base_url"], api_key=cfg.get("api_key", ""))


def _use_json(flag: bool) -> bool:
    return flag


def _resolve_workspace() -> str:
    manifest = load_manifest()
    if manifest and manifest.get("workspace_id"):
        return manifest["workspace_id"]

    with _client() as c:
        mine = c.list_workspaces()
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


def _default_cartridge_id() -> str:
    manifest = load_manifest()
    return (manifest or {}).get("default_cartridge_id", "")


def _err(e: CartridgeError) -> None:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
    with CartridgeClient(base_url=base_url, api_key=api_key) as c:
        try:
            user = c.whoami()
            save_config(username=user["name"])
            console.print(f"[green]Authenticated as {user['name']}[/green]")
        except CartridgeError:
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

_CODEX_HOME_MARKERS = (
    "sessions",
    "config.toml",
    "auth.json",
    ".codex-global-state.json",
    "state_5.sqlite",
)

_CODEX_MACOS_DESKTOP_MARKERS = (
    "Library/Application Support/Codex",
    "Library/Caches/com.openai.codex",
    "Library/Logs/com.openai.codex",
    "Library/Preferences/com.openai.codex.plist",
)

_CODEX_LINUX_DESKTOP_MARKERS = (
    ".config/Codex",
    ".cache/com.openai.codex",
)

_CODEX_WINDOWS_DESKTOP_MARKERS = (
    "AppData/Roaming/Codex",
    "AppData/Local/Codex",
    "AppData/Local/com.openai.codex",
)


def _codex_present() -> bool:
    home = Path.home()
    codex_home = home / ".codex"
    if any((codex_home / marker).exists() for marker in _CODEX_HOME_MARKERS):
        return True

    if sys.platform == "darwin":
        return any((home / marker).exists() for marker in _CODEX_MACOS_DESKTOP_MARKERS)
    if sys.platform.startswith("linux"):
        return any((home / marker).exists() for marker in _CODEX_LINUX_DESKTOP_MARKERS)
    if sys.platform.startswith("win"):
        if any((home / marker).exists() for marker in _CODEX_WINDOWS_DESKTOP_MARKERS):
            return True
        packages = home / "AppData" / "Local" / "Packages"
        return packages.is_dir() and any(packages.glob("OpenAI.Codex_*"))

    return False


def _agent_present(agent: str) -> bool:
    """True if the agent is usable on this machine (binary on PATH or config dir exists)."""
    import shutil

    if shutil.which(_AGENT_BINARY[agent]):
        return True
    if agent == "codex":
        return _codex_present()
    if agent == "cursor":
        return (Path.home() / ".cursor").is_dir()
    return False


def _detected_agents() -> list[str]:
    return [a for a in _SUPPORTED_AGENTS if _agent_present(a)]


def _assets_dir(agent: str) -> Path:
    # cli/ and stashai/ are sibling packages — resolve via filesystem layout
    # instead of `from stashai.plugin.assets import assets_dir` which breaks
    # under editable installs when stale namespace-package dirs in the venv
    # shadow the real package (PathFinder runs before the editable finder).
    path = Path(__file__).resolve().parent.parent / "stashai" / "plugin" / "assets" / agent
    if not path.is_dir():
        raise FileNotFoundError(f"No plugin assets for agent '{agent}' at {path}")
    return path


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
    root = _assets_dir("cursor")
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

    src = _assets_dir("cursor") / "stash.mdc"
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
        "commands make network requests so that we can upload session ",
        "transcripts to the remote server.",
    )
    answer = questionary.confirm(
        "Allow codex bash commands to make outbound network requests?",
        default=True,
    ).ask()
    return True if answer is None else bool(answer)


def _merge_snippet_into_toml(existing: str, snippet: str) -> tuple[str, str]:
    """Merge snippet sections into existing TOML without creating duplicates.

    If a section header like [features] already exists in the config, inject
    the snippet's keys for that section into the existing section instead of
    appending a duplicate header.
    """
    import re

    section_re = re.compile(r"^\[([^\]]+)\]\s*$")
    key_re = re.compile(r"^([A-Za-z0-9_.-]+)\s*=")
    existing_lines = existing.splitlines()
    existing_sections: dict[str, int] = {}
    section_end: dict[str, int] = {}
    existing_keys: dict[str, set[str]] = {}
    current_section: str | None = None

    for idx, line in enumerate(existing_lines):
        section_match = section_re.match(line)
        if section_match:
            if current_section is not None:
                section_end[current_section] = idx
            current_section = section_match.group(1)
            existing_sections[current_section] = idx
            existing_keys.setdefault(current_section, set())
            continue

        key_match = key_re.match(line.strip())
        if current_section is not None and key_match:
            existing_keys.setdefault(current_section, set()).add(key_match.group(1))

    if current_section is not None:
        section_end[current_section] = len(existing_lines)

    if not existing_sections:
        return existing, snippet

    snippet_blocks: list[tuple[str, list[str]]] = []
    pending: list[str] = []
    current_block_section: str | None = None
    current_block: list[str] = []

    for line in snippet.splitlines():
        section_match = section_re.match(line)
        if section_match:
            if current_block_section is not None:
                snippet_blocks.append((current_block_section, current_block))
            current_block_section = section_match.group(1)
            current_block = [*pending, line]
            pending = []
        elif current_block_section is None:
            pending.append(line)
        else:
            current_block.append(line)

    if current_block_section is not None:
        snippet_blocks.append((current_block_section, current_block))

    append_blocks: list[str] = []
    inject_into_existing: dict[str, list[str]] = {}

    for section, block in snippet_blocks:
        if section not in existing_sections:
            append_blocks.extend(block)
            continue

        for line in block:
            stripped = line.strip()
            key_match = key_re.match(stripped)
            if not key_match:
                continue
            key = key_match.group(1)
            if key in existing_keys.get(section, set()):
                continue
            inject_into_existing.setdefault(section, []).append(line)
            existing_keys.setdefault(section, set()).add(key)

    for section, keys in sorted(
        inject_into_existing.items(),
        key=lambda item: section_end[item[0]],
        reverse=True,
    ):
        insert_at = section_end[section]
        existing_lines[insert_at:insert_at] = keys

    merged_existing = "\n".join(existing_lines)
    cleaned_snippet = "\n".join(append_blocks)
    cleaned_snippet = re.sub(r"\n{3,}", "\n\n", cleaned_snippet)
    return merged_existing, cleaned_snippet


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
    root = _assets_dir("codex")
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
        existing, snippet = _merge_snippet_into_toml(existing, snippet)
        sep = "\n" if existing and not existing.endswith("\n") else ""
        cfg_path.write_text(f"{existing}{sep}\n{_CODEX_MARKER}\n{snippet}\n")

    agents_src = root / "AGENTS.md"
    agents_dest = Path.home() / ".codex" / "AGENTS.md"
    if agents_src.exists():
        _upsert_agents_md(agents_dest, agents_src.read_text())

    return (status_, f"{hooks_dest} + merged {cfg_path} + {agents_dest}")


def _install_opencode(force: bool) -> tuple[str, str]:
    root = _assets_dir("opencode")
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
        expected = str(_assets_dir("opencode") / "plugin.ts")
        return expected in (cfg.get("plugin") or [])
    return False


@app.command()
def whoami(as_json: bool = typer.Option(False, "--json")):
    """Show profile."""
    with _client() as c:
        try:
            data = c.whoami()
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_user(data)


# ===========================================================================
# Workspaces
# ===========================================================================

ws_app = typer.Typer(help="Stash Workspace management.")
app.add_typer(ws_app, name="workspaces")


@ws_app.command("list")
def ws_list(as_json: bool = typer.Option(False, "--json")):
    """List workspaces."""
    with _client() as c:
        try:
            data = c.list_workspaces()
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_workspaces(data, title="Workspaces")


@ws_app.command("create")
def ws_create(
    name: str = typer.Argument(...),
    description: str = typer.Option(""),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create workspace."""
    with _client() as c:
        try:
            data = c.create_workspace(name, description=description)
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[bold]{data['name']}[/bold]  Members: {data.get('member_count', '?')}")
        console.print(f"ID: {data['id']}  Invite: {data['invite_code']}")


@ws_app.command("members")
def ws_members(
    workspace_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")
):
    """List workspace members."""
    with _client() as c:
        try:
            data = c.workspace_members(workspace_id)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_members(data)


# ===========================================================================
# Discover (public catalog of Cartridges)
# ===========================================================================


def _web_app_url() -> str:
    """Map the configured API base_url to the matching web app URL."""
    api = load_config().get("base_url", PRODUCTION_BASE_URL)
    if api.startswith("https://api."):
        return api.replace("https://api.", "https://app.", 1)
    if "localhost" in api or "127.0.0.1" in api:
        return "http://localhost:3000"
    return api


def _cartridge_url(stash: dict) -> str:
    return f"{_web_app_url()}/cartridges/{stash['slug']}"


@app.command("browse")
def browse(
    query: str = typer.Argument("", help="Optional search query."),
    sort: str = typer.Option("trending", "--sort", help="trending | newest | popular"),
    pick: bool = typer.Option(
        True, "--pick/--no-pick", help="Open an interactive picker (default) or print a flat list."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Browse the public Stash catalog. Works from any directory — no workspace binding required."""
    with _client() as c:
        try:
            data = c.list_discover_stashes(query=query, sort=sort)
        except CartridgeError as e:
            _err(e)

    cartridges = data.get("cartridges", [])
    if as_json:
        output_json(cartridges)
        return

    if not cartridges:
        console.print("[yellow]No public Cartridges match your filters.[/yellow]")
        return

    if not pick:
        for stash in cartridges:
            owner = stash.get("owner_display_name") or stash.get("owner_name") or "unknown"
            console.print(
                f"[bold]{stash['title']}[/bold]  [dim]by {owner} in {stash['workspace_name']}[/dim]  "
                f"{stash['item_count']} items · {stash['view_count']} views"
            )
            if stash.get("description"):
                console.print(f"  [dim]{stash['description']}[/dim]")
        return

    choices = []
    for stash in cartridges:
        owner = stash.get("owner_display_name") or stash.get("owner_name") or "unknown"
        label = (
            f"{stash['title']:<32} by {owner:<14} "
            f"({stash['item_count']} items, {stash['view_count']} views)"
        )
        choices.append(questionary.Choice(label, value=stash))
    choices.append(questionary.Choice("(quit)", value=None))

    picked = questionary.select("Pick a Stash:", choices=choices).ask()
    if not picked:
        return

    summary = picked.get("description") or "(no description)"
    console.print(
        Panel(
            Text.assemble(
                (picked["title"] + "\n", "bold"),
                (summary + "\n\n", ""),
                (f"by {picked.get('owner_display_name') or picked['owner_name']}  ", "dim"),
                (
                    f"{picked['item_count']} items · {picked['view_count']} views · "
                    f"{picked['workspace_name']}",
                    "dim",
                ),
            ),
            title="Stash",
            border_style="cyan",
        )
    )

    action = questionary.select(
        "What now?",
        choices=[
            questionary.Choice("Open in browser", value="open"),
            questionary.Choice("Add to current workspace", value="add"),
            questionary.Choice("Print share URL", value="url"),
            questionary.Choice("Cancel", value=None),
        ],
    ).ask()
    if not action:
        return

    url = f"{_web_app_url()}/cartridges/{picked['slug']}"
    if action == "open":
        import webbrowser

        webbrowser.open(url)
        console.print(f"[green]Opened[/green] {url}")
    elif action == "url":
        console.print(url)
    elif action == "add":
        workspace_id = _resolve_workspace()
        with _client() as c:
            try:
                c.add_external_cartridge(picked["slug"], workspace_id)
            except CartridgeError as e:
                _err(e)
        console.print(f"[green]Added[/green] {picked['title']} to workspace {workspace_id}")


# ===========================================================================
# Share — publish a session as a public Stash
# ===========================================================================


def _find_session_jsonl(session_id: str) -> Path | None:
    """Locate the .jsonl file for a given session ID under ~/.claude/projects/."""
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return None
    for project_dir in projects.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            with open(jsonl) as f:
                for i, raw in enumerate(f):
                    if i > 5:
                        break
                    try:
                        line = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if line.get("sessionId") == session_id:
                        return jsonl
    return None


def _current_session_id() -> str | None:
    """Read the active session ID from the Stash plugin state file,
    falling back to the most recently modified JSONL in the current
    project's Claude directory."""
    state_file = Path.home() / ".claude" / "plugins" / "data" / "stash" / "state.json"
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            sid = data.get("session_id") or ""
            if sid and _find_session_jsonl(sid):
                return sid
        except Exception:
            pass

    # Fallback: find the most recently modified JSONL for the current working directory
    cwd = str(Path.cwd())
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return None
    for project_dir in sorted(projects.iterdir(), key=lambda p: p.name, reverse=True):
        if not project_dir.is_dir():
            continue
        # Claude Code encodes the cwd path as the project dir name
        decoded = project_dir.name.replace("-", "/", 1).replace("-", "/")
        if not decoded.startswith("/"):
            decoded = "/" + decoded
        # Check if this project dir could match our cwd
        jsonls = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for jsonl in jsonls:
            with open(jsonl) as f:
                for i, raw in enumerate(f):
                    if i > 5:
                        break
                    try:
                        line = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    file_cwd = line.get("cwd", "")
                    if file_cwd and cwd.startswith(file_cwd):
                        sid = line.get("sessionId", "") or jsonl.stem
                        if sid:
                            return sid
    return None


def _extract_session_bookends(raw_jsonl: str) -> tuple[str, str, str]:
    """Extract (title, first_user_prompt, last_assistant_message) from a transcript.

    Returns the bookends of the conversation: the question that kicked it off
    and the final answer — which is usually the investigation summary.
    """
    first_user = ""
    last_assistant = ""
    title = ""

    for raw_line in raw_jsonl.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            continue

        if obj.get("type") == "ai-title":
            title = obj.get("aiTitle") or obj.get("title") or ""
            continue

        msg = obj.get("message")
        if not msg:
            continue
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not content:
            continue

        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        text_parts = []
        for block in blocks:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and block.get("text", "").strip()
            ):
                text_parts.append(block["text"].strip())

        if not text_parts:
            continue
        combined = "\n\n".join(text_parts)

        if role == "user" and not first_user:
            first_user = combined
        elif role == "assistant":
            last_assistant = combined

    return title, first_user, last_assistant


@app.command("share")
def share_session(
    title: str = typer.Option("", "--title", "-t", help="Title for the shared Stash."),
    session_id: str = typer.Option(
        "", "--session", "-s", help="Session ID. Auto-detected if omitted."
    ),
    files: list[str] = typer.Option([], "--file", "-f", help="Files to attach (repeatable)."),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Share a session as a public Stash.

    Publishes a focused summary (the question + finding), the full conversation
    transcript, and any attached files as a single public Stash.
    """
    _require_auth()
    telemetry.record("share")
    ws = workspace_id or _resolve_workspace()

    # Resolve session ID
    sid = session_id or _current_session_id()
    if not sid:
        console.print("[red]Could not detect session. Pass --session <id> explicitly.[/red]")
        raise typer.Exit(1)

    # Find and read the JSONL transcript
    jsonl_path = _find_session_jsonl(sid)
    if not jsonl_path:
        console.print(f"[red]Transcript file not found for session {sid[:8]}…[/red]")
        raise typer.Exit(1)

    raw_jsonl = jsonl_path.read_text(errors="replace")
    ai_title, first_user, last_assistant = _extract_session_bookends(raw_jsonl)

    if not last_assistant:
        console.print("[red]No assistant messages found in this session.[/red]")
        raise typer.Exit(1)

    page_title = title or ai_title or f"Session {sid[:8]}"

    # Build the summary page
    summary_parts = []
    if first_user:
        summary_parts.append(f"## Question\n\n{first_user}")
    summary_parts.append(f"## Finding\n\n{last_assistant}")
    summary_md = "\n\n---\n\n".join(summary_parts)

    # Build the full transcript page
    full_md = _transcript_to_markdown(raw_jsonl)

    # Discover subagent transcripts
    subagents_dir = jsonl_path.parent / jsonl_path.stem / "subagents"
    subagent_entries: list[tuple[str, str, str]] = []  # (label, raw_jsonl, jsonl_path)
    if subagents_dir.is_dir():
        for sa_jsonl in sorted(subagents_dir.glob("agent-*.jsonl")):
            meta_path = sa_jsonl.with_suffix("").with_suffix(".meta.json")
            label = sa_jsonl.stem
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                desc = meta.get("description", "")
                name = meta.get("name", "")
                label = desc or name or label
            sa_raw = sa_jsonl.read_text(errors="replace")
            subagent_entries.append((label, sa_raw, str(sa_jsonl)))

    console.print(f"[dim]Sharing session {sid[:8]}…[/dim]")

    with _client() as c:
        # Create a folder for this session, then drop Summary + Full Transcript inside.
        folder = c.create_folder(ws, page_title)
        c.create_page(ws, "Summary", content=summary_md, folder_id=folder["id"])
        c.create_page(ws, "Full Transcript", content=full_md, folder_id=folder["id"])

        for sa_label, sa_raw, _sa_path in subagent_entries:
            sa_md = _transcript_to_markdown(sa_raw)
            c.create_page(ws, f"Subagent: {sa_label}", content=sa_md, folder_id=folder["id"])
            console.print(f"  [dim]Included subagent: {sa_label}[/dim]")

        cartridge_items: list[dict] = [
            {"object_type": "folder", "object_id": folder["id"], "position": 0},
        ]

        # Upload attached files
        for fp in files:
            p = Path(fp)
            if not p.exists():
                console.print(f"[yellow]Skipping {fp} (not found)[/yellow]")
                continue
            uploaded = c.upload_ws_file(ws, str(p))
            cartridge_items.append(
                {
                    "object_type": "file",
                    "object_id": uploaded["id"],
                    "position": len(cartridge_items),
                    "label_override": p.name,
                }
            )
            console.print(f"  [dim]Attached {p.name}[/dim]")

        # Upload the full transcript blob (may already exist via hooks — that's fine)
        try:
            c.upload_transcript(
                ws, sid, str(jsonl_path), agent_name="claude", cwd=str(jsonl_path.parent)
            )
        except CartridgeError as e:
            if e.status_code != 409:
                raise

        for sa_label, _sa_raw, sa_path in subagent_entries:
            sa_session_id = Path(sa_path).stem
            try:
                c.upload_transcript(
                    ws,
                    sa_session_id,
                    sa_path,
                    agent_name="claude-subagent",
                    cwd=str(jsonl_path.parent),
                )
            except CartridgeError as e:
                if e.status_code != 409:
                    raise

        # Create the public Stash and publish the underlying items
        # so the anonymous URL works immediately.
        bundle = c.publish_cartridge(
            ws,
            title=page_title,
            description="Shared session Stash",
            items=cartridge_items,
        )

    public_url = bundle["url"]
    console.print(f"\n[green bold]Shared![/green bold]  {public_url}")


_UPLOAD_TEXT_EXTENSIONS = {
    ".bash",
    ".bib",
    ".c",
    ".cfg",
    ".cpp",
    ".csv",
    ".fish",
    ".go",
    ".h",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".lua",
    ".md",
    ".mdx",
    ".org",
    ".pl",
    ".py",
    ".r",
    ".rb",
    ".rs",
    ".rst",
    ".sh",
    ".sql",
    ".svg",
    ".swift",
    ".tex",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}


def _is_upload_text_file(path: Path) -> bool:
    return path.suffix.lower() in _UPLOAD_TEXT_EXTENSIONS


def _has_hidden_part(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _upload_file_list(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(
        path
        for path in target.rglob("*")
        if path.is_file() and not _has_hidden_part(path.relative_to(target))
    )


def _upload_folder_for_file(
    c: CartridgeClient,
    workspace_id: str,
    root_folder_id: str,
    folder_cache: dict[tuple[str, str], str],
    relative_path: Path,
) -> str:
    parent_id = root_folder_id
    for folder_name in relative_path.parts[:-1]:
        key = (parent_id, folder_name)
        if key not in folder_cache:
            folder_cache[key] = c.create_folder(
                workspace_id,
                folder_name,
                parent_folder_id=parent_id,
            )["id"]
        parent_id = folder_cache[key]
    return parent_id


@app.command("upload")
def upload(
    path: str = typer.Argument(..., help="Directory or file to upload."),
    name: str = typer.Option("", "--name", "-n", help="Name for the uploaded folder."),
    workspace_id: str = typer.Option(None, "--ws"),
    stash: str = typer.Option(
        "",
        "--stash",
        help=(
            "Also bundle the upload into a new Stash with this title. Omit "
            "for a workspace-only upload (the common case)."
        ),
    ),
    public: bool = typer.Option(
        True,
        "--public/--private",
        help="Stash visibility (only meaningful with --stash).",
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Upload local files into a workspace folder.

    Default: upload only — files land in a workspace folder, and the
    returned ``app_url`` is the workspace link your teammates can already
    follow. **No Stash is created.**

    Pass ``--stash <title>`` to *also* bundle the upload into a shareable
    Stash. Use a Stash when you're publishing a curated bundle of related
    artifacts (a project writeup with its supporting files, a research
    thread with its sources) — not as a wrapper around every single
    upload."""
    _require_auth()
    telemetry.record("upload")
    target = Path(path)
    if not target.exists():
        console.print(f"[red]Not found: {path}[/red]")
        raise typer.Exit(1)

    files = _upload_file_list(target)
    if not files:
        console.print(f"[red]No files found in {path}[/red]")
        raise typer.Exit(1)

    root_name = name or (target.stem if target.is_file() else target.name)
    stash_title = stash.strip() or root_name
    create_cartridge = bool(stash)
    ws = workspace_id or _resolve_workspace()
    console.print(f"[dim]Uploading {len(files)} file(s) as '{root_name}'...[/dim]")

    with _client() as c:
        root_folder = c.create_folder(ws, root_name)
        folder_cache: dict[tuple[str, str], str] = {}
        cartridge_items: list[dict] = []
        if target.is_dir():
            cartridge_items.append(
                {"object_type": "folder", "object_id": root_folder["id"], "position": 0}
            )

        for file_path in files:
            relative_path = (
                file_path.relative_to(target) if target.is_dir() else Path(file_path.name)
            )
            folder_id = _upload_folder_for_file(
                c,
                ws,
                root_folder["id"],
                folder_cache,
                relative_path,
            )

            if _is_upload_text_file(file_path):
                content = file_path.read_text(errors="replace")
                page = c.create_page(ws, file_path.name, content=content, folder_id=folder_id)
                if target.is_file():
                    cartridge_items.append(
                        {
                            "object_type": "page",
                            "object_id": page["id"],
                            "position": len(cartridge_items),
                            "label_override": str(relative_path),
                        }
                    )
                console.print(f"  [dim]Page: {relative_path}[/dim]")
                continue

            uploaded = c.upload_ws_file(ws, str(file_path))
            c.create_page(
                ws,
                file_path.name,
                content=_markdown_snippet(uploaded),
                folder_id=folder_id,
            )
            cartridge_items.append(
                {
                    "object_type": "file",
                    "object_id": uploaded["id"],
                    "position": len(cartridge_items),
                    "label_override": str(relative_path),
                }
            )
            console.print(f"  [dim]File: {relative_path}[/dim]")

        folder_url = f"{_web_app_url()}/workspaces/{ws}/folders/{root_folder['id']}"
        result: dict = {"folder": root_folder, "app_url": folder_url}

        if create_cartridge:
            if public:
                bundle = c.publish_cartridge(
                    ws,
                    title=stash_title,
                    description=f"Uploaded from {target.name}",
                    items=cartridge_items,
                )
                stash_row = bundle["cartridge"]
                stash_url = bundle["url"]
            else:
                stash_row = c.create_cartridge(
                    ws,
                    title=stash_title,
                    description=f"Uploaded from {target.name}",
                    items=cartridge_items,
                )
                stash_url = _cartridge_url(stash_row)
            result["stash"] = stash_row
            result["url"] = stash_url

    if _use_json(as_json):
        output_json(result)
        return
    if create_cartridge:
        console.print(
            f"\n[green bold]Uploaded![/green bold]  {result['url']}\n"
            f"[dim]Folder: {root_folder['id']}  Stash: {result['stash']['id']}[/dim]"
        )
    else:
        console.print(
            f"\n[green bold]Uploaded![/green bold]  {folder_url}\n"
            f"[dim]Folder: {root_folder['id']}  "
            f"(pass --stash <title> to also bundle into a shareable Stash)[/dim]"
        )


def _parse_cartridge_slug(url_or_slug: str) -> str:
    """Extract a Stash slug from a full URL or bare slug."""
    url_or_slug = url_or_slug.strip().rstrip("/")
    if "/cartridges/" in url_or_slug:
        return url_or_slug.split("/cartridges/")[-1]
    return url_or_slug


@app.command("read")
def read_cartridge(
    url: str = typer.Argument(..., help="Stash URL or slug."),
):
    """Read a public Stash and print its contents."""
    slug = _parse_cartridge_slug(url)
    with _client() as c:
        text = c.get_cartridge_text(slug)
    console.print(text)


# ===========================================================================
# Cartridges
# ===========================================================================

stashes_app = typer.Typer(help="Cartridges — shareable sets of pages, sessions, tables, and files.")
app.add_typer(stashes_app, name="cartridges")


@stashes_app.command("list")
def stashes_list(
    workspace_id: str = typer.Argument(None, help="Workspace ID; falls back to .stash."),
    as_json: bool = typer.Option(False, "--json"),
):
    """List Cartridges in a workspace."""
    ws_id = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.list_stashes(ws_id)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if not data:
        console.print("[dim]No Cartridges in this workspace.[/dim]")
        return
    for v in data:
        flag = f"[cyan]{v['access']}[/cyan]"
        console.print(
            f"[bold]{v['title']}[/bold]  {flag}  /cartridges/{v['slug']}  "
            f"[dim]({len(v['items'])} items, viewed {v['view_count']}x)[/dim]"
        )


@stashes_app.command("create")
def stashes_create(
    title: str = typer.Argument(..., help="Stash title."),
    workspace_id: str = typer.Option("", "--workspace", help="Workspace ID; falls back to .stash."),
    description: str = typer.Option("", "--description"),
    public: bool = typer.Option(False, "--public", help="Publish immediately."),
    discover: bool = typer.Option(False, "--discover", help="List the public Stash in Discover."),
    items_json: str = typer.Option(
        "[]",
        "--items",
        help='JSON array of items: [{"object_type":"folder","object_id":"..."}, ...]',
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a Stash. Pass --items as JSON to attach resources up front."""
    if discover and not public:
        console.print("[red]--discover requires --public.[/red]")
        raise typer.Exit(1)
    ws_id = workspace_id or _resolve_workspace()
    items = json.loads(items_json)
    with _client() as c:
        try:
            if public:
                bundle = c.publish_cartridge(
                    ws_id,
                    title=title,
                    description=description,
                    discoverable=discover,
                    items=items,
                )
                stash = bundle["cartridge"]
            else:
                stash = c.create_cartridge(
                    ws_id,
                    title=title,
                    description=description,
                    discoverable=False,
                    items=items,
                )
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(stash)
        return
    flag = f"[cyan]{stash['access']}[/cyan]"
    if stash.get("discoverable"):
        flag = f"{flag} [cyan]discover[/cyan]"
    console.print(f"[green]Created Stash[/green] '{stash['title']}'  {flag}")
    console.print(f"  ID: {stash['id']}  Slug: {stash['slug']}")
    if stash["access"] == "public":
        console.print(f"  Public URL: [cyan]{_web_app_url()}/cartridges/{stash['slug']}[/cyan]")


@stashes_app.command("publish")
def stashes_publish(
    cartridge_id: str = typer.Argument(...),
    private: bool = typer.Option(False, "--private", help="Make the Stash private."),
    workspace: bool = typer.Option(
        False, "--workspace-access", help="Make the Stash workspace-visible."
    ),
    discover: bool = typer.Option(False, "--discover", help="List the public Stash in Discover."),
):
    """Change a Stash's access level."""
    if discover and (private or workspace):
        console.print("[red]--discover requires public access.[/red]")
        raise typer.Exit(1)
    access = "private" if private else "workspace" if workspace else "public"
    with _client() as c:
        try:
            stash = c.update_cartridge(
                cartridge_id,
                **stash_permissions_for_access(access),
                discoverable=False if access != "public" else discover,
            )
        except CartridgeError as e:
            _err(e)
    if stash["access"] == "public":
        label = "Published to Discover" if stash.get("discoverable") else "Published"
        console.print(
            f"[green]{label}[/green] '{stash['title']}' -> "
            f"[cyan]{_web_app_url()}/cartridges/{stash['slug']}[/cyan]"
        )
    else:
        console.print(f"[yellow]{stash['access'].title()}[/yellow] '{stash['title']}'")


@stashes_app.command("update")
def stashes_update(
    cartridge_id: str = typer.Argument(...),
    title: str | None = typer.Option(None, "--title"),
    description: str | None = typer.Option(None, "--description"),
    access: str | None = typer.Option(
        None,
        "--access",
        help="One of: workspace, private, public.",
    ),
    discover: bool | None = typer.Option(
        None,
        "--discover/--no-discover",
        help="Whether a public Stash appears in Discover.",
    ),
    items_json: str | None = typer.Option(
        None,
        "--items",
        help='Replace items with JSON: [{"object_type":"page","object_id":"..."}, ...]',
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Update a Stash's metadata, access, Discover flag, or item list."""
    fields = {}
    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = description
    if access is not None:
        if access not in {"workspace", "private", "public"}:
            console.print("[red]--access must be workspace, private, or public.[/red]")
            raise typer.Exit(1)
        fields.update(stash_permissions_for_access(access))
    if discover is not None:
        fields["discoverable"] = discover
    if items_json is not None:
        fields["items"] = json.loads(items_json)
    if not fields:
        console.print("[red]Pass at least one field to update.[/red]")
        raise typer.Exit(1)

    with _client() as c:
        try:
            stash = c.update_cartridge(cartridge_id, **fields)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(stash)
        return
    flag = f"[cyan]{stash['access']}[/cyan]"
    if stash.get("discoverable"):
        flag = f"{flag} [cyan]discover[/cyan]"
    console.print(f"[green]Updated Stash[/green] '{stash['title']}'  {flag}")


@stashes_app.command("default")
def stashes_default(
    cartridge_id: str = typer.Argument(
        "", help="Stash ID to receive this repo's streamed sessions."
    ),
    clear: bool = typer.Option(False, "--clear", help="Clear this repo's default Stash."),
    workspace_id: str = typer.Option("", "--workspace", help="Workspace ID; falls back to .stash."),
):
    """Set which Stash this repo streams sessions into by default."""
    if clear:
        try:
            write_manifest({"default_cartridge_id": ""})
        except FileNotFoundError:
            console.print("[red]No .stash file found. Run `stash connect` first.[/red]")
            raise typer.Exit(1)
        console.print("[green]Cleared default Stash.[/green]")
        return

    if not cartridge_id:
        current = _default_cartridge_id()
        console.print(current or "(none)")
        return

    ws_id = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            cartridges = c.list_stashes(ws_id)
        except CartridgeError as e:
            _err(e)
    if not any(stash["id"] == cartridge_id for stash in cartridges):
        console.print("[red]Default Stash must belong to the active workspace.[/red]")
        raise typer.Exit(1)

    try:
        write_manifest({"default_cartridge_id": cartridge_id})
    except FileNotFoundError:
        console.print("[red]No .stash file found. Run `stash connect` first.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Default Stash set[/green] {cartridge_id}")


@stashes_app.command("delete")
def stashes_delete(cartridge_id: str = typer.Argument(...)):
    """Delete a Stash. The underlying resources are not touched."""
    with _client() as c:
        try:
            c.delete_cartridge(cartridge_id)
        except CartridgeError as e:
            _err(e)
    console.print(f"[green]Deleted Stash[/green] {cartridge_id}")


@stashes_app.command("add-external")
def stashes_add_external(
    slug: str = typer.Argument(..., help="Public slug of the Stash."),
    workspace_id: str = typer.Option("", "--workspace", help="Workspace ID; falls back to .stash."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Fork an external Stash into a workspace."""
    ws_id = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            stash = c.add_external_cartridge(slug, ws_id)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(stash)
        return
    console.print(f"[green]Forked external Stash[/green] '{stash['title']}'")
    console.print(f"  Open it: [cyan]{_web_app_url()}/cartridges/{stash['slug']}[/cyan]")


@stashes_app.command("remove-external")
def stashes_remove_external(
    cartridge_id: str = typer.Argument(..., help="Stash ID."),
    workspace_id: str = typer.Option("", "--workspace", help="Workspace ID; falls back to .stash."),
):
    """Remove a forked external Stash from a workspace."""
    ws_id = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.remove_external_cartridge(ws_id, cartridge_id)
        except CartridgeError as e:
            _err(e)
    console.print(f"[green]Removed forked Stash[/green] {cartridge_id}")


@stashes_app.command("invites")
def stashes_invites(as_json: bool = typer.Option(False, "--json")):
    """List Cartridge invites pending for you (shared with you, awaiting action)."""
    with _client() as c:
        try:
            data = c.list_cartridge_invites()
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if not data:
        console.print("[dim]No pending invites.[/dim]")
        return
    for inv in data:
        console.print(
            f"  [bold]{inv.get('cartridge_title')}[/bold]  "
            f"[dim]from {inv.get('invited_by_display_name')} — {inv.get('permission')} "
            f"— {inv.get('id')}[/dim]"
        )


@stashes_app.command("dismiss-invite")
def stashes_dismiss_invite(invite_id: str = typer.Argument(...)):
    """Dismiss a pending Cartridge invite."""
    with _client() as c:
        try:
            c.dismiss_cartridge_invite(invite_id)
        except CartridgeError as e:
            _err(e)
    console.print(f"[green]Dismissed invite[/green] {invite_id}")


@stashes_app.command("snapshot-source")
def stashes_snapshot_source(
    cartridge_id: str = typer.Argument(...),
    source: str = typer.Option(
        ..., "--source", help="Connected-source id (from `stash sources ls`)."
    ),
    path: str = typer.Option(..., "--path", help="Document path within the source."),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Snapshot one connected-source document into a Cartridge as a page."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.snapshot_source_into_cartridge(ws, cartridge_id, source, path)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(f"[green]Snapshotted[/green] {path}  [dim]→ page {data.get('id')}[/dim]")


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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
            _err(e)
    console.print(f"[green]Revoked invite token {token_id[:8]}…[/green]")


# ===========================================================================
# Files: folders (nestable) + pages
# ===========================================================================

files_app = typer.Typer(help="Files — folders, pages, and uploaded files.")
app.add_typer(files_app, name="files")


@files_app.command("tree")
def files_tree(
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show the nested folder + page tree for the workspace."""
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            data = c.get_workspace_tree(ws)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return

    def _print_folder(folder: dict, depth: int) -> None:
        pad = "  " * depth
        console.print(f"{pad}[bold]{folder['name']}/[/bold]  (id: {str(folder['id'])[:8]})")
        for sub in folder.get("folders", []):
            _print_folder(sub, depth + 1)
        for p in folder.get("pages", []):
            console.print(f"{pad}  {p['name']}  (id: {str(p['id'])[:8]})")

    for folder in data.get("folders", []):
        _print_folder(folder, 0)
    for p in data.get("pages", []):
        console.print(f"  {p['name']}  (id: {str(p['id'])[:8]})")


@files_app.command("folders")
def files_folders(
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Flat list of every folder in the workspace."""
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            data = c.list_folders(ws)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No folders.[/dim]")
        else:
            for f in data:
                parent = (
                    f"  parent: {str(f['parent_folder_id'])[:8]}"
                    if f.get("parent_folder_id")
                    else ""
                )
                console.print(f"  {f['name']}  (id: {str(f['id'])[:8]}){parent}")


@files_app.command("create-folder")
def files_create_folder(
    name: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    parent: str = typer.Option(None, "--parent", help="parent folder id (omit for root)"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a folder. Omit --parent to create at workspace root."""
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            data = c.create_folder(ws, name, parent_folder_id=parent)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Folder '{data['name']}' created.[/green]  ID: {data['id']}")


@files_app.command("edit-folder")
def files_edit_folder(
    folder_id: str = typer.Argument(...),
    name: str = typer.Option(None, "--name", help="Rename the folder."),
    parent: str = typer.Option(None, "--parent", help="Move under this parent folder id."),
    to_root: bool = typer.Option(False, "--to-root", help="Move to workspace root."),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Rename and/or reparent a folder."""
    if parent and to_root:
        console.print("[red]--parent and --to-root are mutually exclusive[/red]")
        raise typer.Exit(1)
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.update_folder(
                ws,
                folder_id,
                name=name,
                parent_folder_id=parent,
                move_to_root=to_root,
            )
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Folder updated.[/green] {data['name']}  [dim]{data['id']}[/dim]")


@files_app.command("pages")
def files_pages(
    workspace_id: str = typer.Option(None, "--ws"),
    all_: bool = typer.Option(False, "--all", help="list pages across every workspace"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List pages. --all for cross-workspace, default for the active workspace."""
    with _client() as c:
        try:
            data = c.all_pages() if all_ else c.list_pages(workspace_id or _resolve_workspace())
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No pages.[/dim]")
            return
        for p in data:
            path = "/".join(p.get("folder_path") or [])
            label = f"{path}/{p['name']}" if path else p["name"]
            ws = f" [{p.get('workspace_name', '')}]" if p.get("workspace_name") else ""
            console.print(f"  {label}{ws}  (id: {str(p['id'])[:8]})")


def _markdown_snippet(file_resp: dict) -> str:
    """Build an image or link markdown snippet from an uploaded FileResponse."""
    name = file_resp["name"]
    url = file_resp["url"]
    ct = file_resp.get("content_type", "") or ""
    if ct.startswith("image/"):
        return f"![{name}]({url})"
    return f"[{name}]({url})"


def _prepend_attachments(
    c: CartridgeClient, workspace_id: str, content: str, attach: list[str] | None
) -> str:
    if not attach:
        return content
    snippets = [_markdown_snippet(c.upload_ws_file(workspace_id, p)) for p in attach]
    block = "\n\n".join(snippets)
    return f"{block}\n\n{content}" if content else block


@files_app.command("add-page")
def files_add_page(
    name: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    folder: str = typer.Option(None, "--folder", help="folder id; omit for workspace root"),
    content: str = typer.Option(""),
    page_type: str = typer.Option(
        "markdown", "--type", help="Page type: markdown (default) or html.", case_sensitive=False
    ),
    html_file: str = typer.Option(
        None, "--html-file", help="Local HTML file to load as content for an html page."
    ),
    layout: str = typer.Option(
        None,
        "--layout",
        help="HTML layout: 'responsive' (default) or 'fixed-aspect' for 16:9 slide decks.",
        case_sensitive=False,
    ),
    attach: list[str] = typer.Option(
        None, "--attach", help="Local file path to upload and embed (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a page. --folder drops it into a folder, otherwise it goes to the workspace root."""
    page_type = page_type.lower()
    if page_type not in ("markdown", "html"):
        console.print(f"[red]--type must be 'markdown' or 'html', got: {page_type}[/red]")
        raise typer.Exit(1)
    if layout is not None:
        layout = layout.lower()
        if layout not in ("responsive", "fixed-aspect"):
            console.print(
                f"[red]--layout must be 'responsive' or 'fixed-aspect', got: {layout}[/red]"
            )
            raise typer.Exit(1)
        if page_type != "html":
            console.print("[yellow]--layout only applies to html pages; ignoring[/yellow]")
            layout = None
    if page_type == "html" and html_file:
        if not Path(html_file).is_file():
            console.print(f"[red]Not a file: {html_file}[/red]")
            raise typer.Exit(1)
        html_body = Path(html_file).read_text()
    elif page_type == "html":
        html_body = content
        content = ""
    else:
        html_body = ""

    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            for p in attach or []:
                if not Path(p).is_file():
                    console.print(f"[red]Not a file: {p}[/red]")
                    raise typer.Exit(1)
            if page_type == "markdown":
                body = _prepend_attachments(c, ws, content, attach)
            else:
                body = ""
                if attach:
                    console.print("[yellow]--attach is ignored for html pages[/yellow]")
            data = c.create_page(
                ws,
                name,
                content=body,
                folder_id=folder,
                content_type=page_type,
                content_html=html_body,
                html_layout=layout,
            )
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(
            f"[green]Page '{data['name']}' created.[/green]  ID: {data['id']}  "
            f"Type: {data.get('content_type', 'markdown')}"
        )


@files_app.command("read-page")
def files_read_page(
    page_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Read a page's content."""
    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            data = c.get_page(ws, page_id)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[bold]{data['name']}[/bold]\n")
        if data.get("content_type") == "html":
            console.print(data.get("content_html", ""))
        else:
            console.print(data.get("content_markdown", ""))


@files_app.command("edit-page")
def files_edit_page(
    page_id: str = typer.Argument(...),
    content: str = typer.Option(None, "--content"),
    name: str = typer.Option(None, "--name"),
    workspace_id: str = typer.Option(None, "--ws"),
    page_type: str = typer.Option(
        None, "--type", help="Switch the page to this type: markdown or html.", case_sensitive=False
    ),
    html_file: str = typer.Option(
        None, "--html-file", help="Local HTML file to load as content_html."
    ),
    layout: str = typer.Option(
        None,
        "--layout",
        help="Switch HTML layout: 'responsive' or 'fixed-aspect' (16:9 slide decks).",
        case_sensitive=False,
    ),
    attach: list[str] = typer.Option(
        None, "--attach", help="Local file path to upload and prepend (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Update a page. Reads from stdin if --content not given."""
    html_body: str | None = None
    if html_file:
        if not Path(html_file).is_file():
            console.print(f"[red]Not a file: {html_file}[/red]")
            raise typer.Exit(1)
        html_body = Path(html_file).read_text()
    if content is None and not sys.stdin.isatty():
        content = sys.stdin.read()
    if page_type:
        page_type = page_type.lower()
        if page_type not in ("markdown", "html"):
            console.print(f"[red]--type must be 'markdown' or 'html', got: {page_type}[/red]")
            raise typer.Exit(1)
    if layout is not None:
        layout = layout.lower()
        if layout not in ("responsive", "fixed-aspect"):
            console.print(
                f"[red]--layout must be 'responsive' or 'fixed-aspect', got: {layout}[/red]"
            )
            raise typer.Exit(1)
    if html_body is not None and page_type is None:
        page_type = "html"
    if page_type == "html" and html_body is None and content is not None:
        html_body = content
        content = None

    with _client() as c:
        try:
            ws = workspace_id or _resolve_workspace()
            for p in attach or []:
                if not Path(p).is_file():
                    console.print(f"[red]Not a file: {p}[/red]")
                    raise typer.Exit(1)
            if attach and page_type != "html":
                base = (
                    content
                    if content is not None
                    else c.get_page(ws, page_id).get("content_markdown", "")
                )
                content = _prepend_attachments(c, ws, base, attach)
            elif attach:
                console.print("[yellow]--attach is ignored for html pages[/yellow]")
            kwargs: dict = {}
            if content is not None:
                kwargs["content"] = content
            if name is not None:
                kwargs["name"] = name
            if page_type is not None:
                kwargs["content_type"] = page_type
            if html_body is not None:
                kwargs["content_html"] = html_body
            if layout is not None:
                kwargs["html_layout"] = layout
            data = c.update_page(ws, page_id, **kwargs)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Page updated.[/green]")


# ===========================================================================
# Sessions
# ===========================================================================

hist_app = typer.Typer(
    help="Sessions — agent transcripts and event logs.", invoke_without_command=True
)
app.add_typer(hist_app, name="sessions")


@hist_app.callback()
def hist_default(
    ctx: typer.Context,
    workspace_id: str = typer.Option(None, "--ws"),
    limit: int = typer.Option(20, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Sessions — agent transcripts and event logs."""
    if ctx.invoked_subcommand is not None:
        return
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.query_events(ws, limit=limit)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for ev in data:
            tool = f" ({ev['tool_name']})" if ev.get("tool_name") else ""
            console.print(
                f"  [{ev['created_at'][:19]}] {ev['agent_name']}/{ev['event_type']}{tool}: {ev['content'][:200]}"
            )


@hist_app.command("agents")
def hist_agents(
    workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")
):
    """List distinct agent names that have logged events in this workspace."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.list_agent_names(ws)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        if not data:
            console.print("[dim]No agents have logged events yet.[/dim]")
        else:
            for name in data:
                console.print(f"  {name}")


@hist_app.command("folders")
def hist_folders(
    workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")
):
    """List session folders (shareable groupings of sessions)."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.list_session_folders(ws)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if not data:
        console.print("[dim]No session folders.[/dim]")
        return
    for f in data:
        console.print(f"  [bold]{f.get('name')}[/bold]  [dim]({f.get('id')})[/dim]")


@hist_app.command("new-folder")
def hist_new_folder(
    name: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a session folder."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.create_session_folder(ws, name)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(f"[green]Created folder[/green] {name}  [dim]({data.get('id')})[/dim]")


@hist_app.command("assign")
def hist_assign(
    session_row_id: str = typer.Argument(..., help="The session row id to move."),
    folder: str = typer.Option(
        None, "--folder", help="Target folder id; omit to move back to ungrouped root."
    ),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Move a session into a session folder (or back to the ungrouped root)."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.assign_session_folder(ws, session_row_id, folder_id=folder)
        except CartridgeError as e:
            _err(e)
    console.print("[green]Session assigned.[/green]")


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
    created_at: str = typer.Option(
        None, "--created-at", help="ISO-8601 timestamp (e.g. 2026-04-22T10:30:00Z)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Push an event to the workspace session stream."""
    telemetry.record("history.push")
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
                default_cartridge_id=_default_cartridge_id(),
                tool_name=tool_name,
                attachments=attachments or None,
                created_at=created_at,
            )
        except CartridgeError as e:
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
    before: str = typer.Option(None, "--before", help="Cursor: ISO timestamp for previous page"),
    after: str = typer.Option(None, "--after", help="Cursor: ISO timestamp for next page"),
    order: str = typer.Option(
        "desc", "--order", help="Sort order: desc (newest first) or asc (oldest first)"
    ),
    all_: bool = typer.Option(False, "--all"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Query events (newest first by default). --all for cross-workspace."""
    telemetry.record("history.query")
    with _client() as c:
        try:
            if all_:
                data = c.all_events(
                    agent_name=agent_name,
                    event_type=event_type,
                    limit=limit,
                    before=before,
                    after=after,
                    order=order,
                )
            else:
                ws = workspace_id or _resolve_workspace()
                data = c.query_events(
                    ws,
                    agent_name=agent_name,
                    event_type=event_type,
                    limit=limit,
                    before=before,
                    after=after,
                    order=order,
                )
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for ev in data:
            tool = f" ({ev['tool_name']})" if ev.get("tool_name") else ""
            console.print(
                f"  [{ev['created_at'][:19]}] {ev['agent_name']}/{ev['event_type']}{tool}: {ev['content'][:200]}"
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


def _transcript_to_markdown(raw_jsonl: str) -> str:
    """Convert a Claude Code .jsonl transcript into readable markdown."""
    lines = []
    for raw_line in raw_jsonl.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            continue

        msg = obj.get("message")
        if not msg:
            if obj.get("type") == "ai-title":
                title = obj.get("title", "")
                if title:
                    lines.append(f"# {title}\n")
            continue

        role = msg.get("role", "")
        content = msg.get("content", "")
        if not content:
            continue

        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")

            if btype == "text" and block.get("text", "").strip():
                prefix = "**User:**" if role == "user" else "**Assistant:**"
                lines.append(f"{prefix}\n\n{block['text'].strip()}\n")

            elif btype == "tool_use":
                name = block.get("name", "tool")
                inp = block.get("input", {})
                if name.lower() in ("bash", "shell"):
                    cmd = inp.get("command", "")
                    lines.append(f"```bash\n$ {cmd}\n```\n")
                elif name.lower() in ("read", "readfile"):
                    lines.append(f"*Read `{inp.get('file_path', '?')}`*\n")
                elif name.lower() in ("edit", "write"):
                    fp = inp.get("file_path", "?")
                    lines.append(f"*{name.title()} `{fp}`*\n")
                else:
                    lines.append(f"*Tool: {name}*\n")

            elif btype == "tool_result":
                text = ""
                sub = block.get("content", "")
                if isinstance(sub, str):
                    text = sub
                elif isinstance(sub, list):
                    text = "\n".join(
                        s.get("text", "")
                        for s in sub
                        if isinstance(s, dict) and s.get("type") == "text"
                    )
                if text.strip():
                    preview = text.strip()[:2000]
                    lines.append(f"```\n{preview}\n```\n")

    return "\n---\n\n".join(lines) if lines else "(empty transcript)"


@hist_app.command("share")
def hist_share(
    session_id: str = typer.Argument(...),
    title: str = typer.Option(
        "", "--title", help="Title for the shared page. Auto-generated if omitted."
    ),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Share a session transcript as a public Stash link.

    Fetches the transcript, formats it as a readable page, publishes it
    in a new Stash, and prints the shareable URL.
    """
    import gzip

    import httpx

    ws = workspace_id or _resolve_workspace()
    cfg = load_config()
    base = cfg["base_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {cfg.get('api_key', '')}"}

    # 1. Fetch transcript
    url = f"{base}/api/v1/workspaces/{ws}/transcripts/{session_id}"
    meta = httpx.get(url, headers=headers, timeout=30).json()
    if "download_url" not in meta:
        console.print(f"[red]{meta.get('detail', 'Transcript not found')}[/red]")
        raise typer.Exit(1)
    raw = httpx.get(meta["download_url"], timeout=60).content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    body = raw.decode("utf-8", errors="replace")

    # 2. Format into markdown
    md = _transcript_to_markdown(body)

    # 3. Create folder + page + public Stash
    page_title = title or f"Session {session_id[:8]}"
    with _client() as c:
        folder = c.create_folder(ws, page_title)
        c.create_page(ws, page_title, content=md, folder_id=folder["id"])
        bundle = c.publish_cartridge(
            ws,
            title=page_title,
            description="Shared session transcript",
            items=[{"object_type": "folder", "object_id": folder["id"]}],
        )

    console.print(f"[green]Shared![/green]  {bundle['url']}")


@hist_app.command("import")
def hist_import(
    workspace_id: str = typer.Option(None, "--ws"),
    agent_name: str = typer.Option(None, "--agent", help="Only import from this agent."),
    limit: int = typer.Option(0, "-n", "--limit", help="Max conversations to import (0 = all)."),
    replace: bool = typer.Option(False, "--replace", help="Replace sessions that already exist."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Import historical conversations from coding agents on this machine.

    Discovers conversations from Claude Code, Cursor, and Codex, then uploads
    them as transcripts to the workspace.
    """
    from .import_history import discover_conversations, summarize_discovery, upload_conversation

    _require_auth()

    agents = [agent_name] if agent_name else None
    conversations = discover_conversations(agents, repo_dir=Path.cwd())

    if not conversations:
        console.print("[dim]No historical conversations found.[/dim]")
        raise typer.Exit(0)

    summary = summarize_discovery(conversations)

    if _use_json(as_json) and not yes:
        output_json({"discovered": summary, "total": len(conversations)})
        raise typer.Exit(0)

    if not as_json:
        console.print("\n[bold]Discovered conversations:[/bold]\n")
        for ag, info in sorted(summary.items()):
            sz = info["total_size_bytes"]
            label = f"{sz // 1024 // 1024} MB" if sz > 1024 * 1024 else f"{sz // 1024} KB"
            console.print(f"  {ag:<12} {info['count']:>4} conversations   ({label})")
        console.print(f"\n  [bold]Total: {len(conversations)} conversations[/bold]")

    if limit > 0:
        conversations = conversations[:limit]

    if not yes:
        ok = questionary.confirm(
            f"Import {len(conversations)} conversations into workspace?", default=True
        ).ask()
        if not ok:
            raise typer.Exit(0)

    ws = workspace_id or _resolve_workspace()

    from rich.progress import Progress

    imported = 0
    errors = 0
    with _client() as c, Progress(console=console) as progress:
        task = progress.add_task("Importing…", total=len(conversations))
        for conv in conversations:
            try:
                upload_conversation(
                    c,
                    ws,
                    conv,
                    default_cartridge_id=_default_cartridge_id(),
                    replace=replace,
                )
                imported += 1
            except CartridgeError:
                errors += 1
            progress.advance(task)

    if _use_json(as_json):
        output_json({"imported": imported, "errors": errors})
    else:
        console.print(f"\n[green]Imported {imported} conversations.[/green]")
        if errors:
            console.print(
                f"[yellow]{errors} failed (likely already imported or too large).[/yellow]"
            )


@hist_app.command("delete")
def hist_delete(
    session_row_id: str = typer.Argument(..., help="Session row id (UUID), not session_id."),
    workspace_id: str = typer.Option(None, "--ws"),
    permanent: bool = typer.Option(False, "--permanent"),
):
    """Move a session to trash. Pass --permanent to wipe it without going through trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.delete_session(ws, session_row_id)
            if permanent:
                c.purge_session(ws, session_row_id)
        except CartridgeError as e:
            _err(e)
    console.print(
        "[green]Session permanently deleted.[/green]"
        if permanent
        else "[green]Session moved to trash.[/green]"
    )


@hist_app.command("restore")
def hist_restore(
    session_row_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Restore a session from trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.restore_session(ws, session_row_id)
        except CartridgeError as e:
            _err(e)
    console.print("[green]Session restored.[/green]")


@hist_app.command("purge")
def hist_purge(
    session_row_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Permanently delete a session already in trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.purge_session(ws, session_row_id)
        except CartridgeError as e:
            _err(e)
    console.print("[green]Session permanently deleted.[/green]")


# ===========================================================================
# Sources — unified VFS over native files/sessions + connected sources
# ===========================================================================

sources_app = typer.Typer(
    help="Sources — browse, read, and search files, sessions, and connected sources."
)
app.add_typer(sources_app, name="sources")


def _print_search(query: str, source: str, workspace_id: str, limit: int, as_json: bool) -> None:
    """Shared body for `stash search` and `stash sources search`."""
    telemetry.record("sources.search")
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.search_sources(ws, query, source=source or None, limit=limit)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if not data:
        console.print("[dim]No matches.[/dim]")
        return
    for hit in data:
        label = hit.get("source_name") or hit.get("source")
        name = hit.get("name") or hit.get("ref") or ""
        console.print(f"  [bold]{name}[/bold]  [dim]({label}: {hit.get('ref')})[/dim]")
        snippet = (hit.get("snippet") or "").replace("\n", " ").strip()
        if snippet:
            console.print(f"    {snippet}")


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Search query."),
    source: str = typer.Option(
        "", "--source", help="Scope to one source handle (omit to search everything)."
    ),
    workspace_id: str = typer.Option(None, "--ws"),
    limit: int = typer.Option(20, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Search everything you can see — files, sessions, and connected sources."""
    _print_search(query, source, workspace_id, limit, as_json)


@sources_app.command("ls")
def sources_ls(
    workspace_id: str = typer.Option(None, "--ws"), as_json: bool = typer.Option(False, "--json")
):
    """List every source you can read here."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.list_sources(ws)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    for s in data:
        console.print(
            f"  [bold]{s['display_name']}[/bold]  [dim]({s['type']}, {s['capability']}) "
            f"→ {s['source']}[/dim]"
        )


@sources_app.command("add")
def sources_add(
    source_type: str = typer.Argument(
        ..., help="github_repo | google_drive | gmail | notion | slack | granola"
    ),
    ref: str = typer.Option(
        "", "--ref", help="external_ref, e.g. a repo 'owner/name' or Gmail address."
    ),
    name: str = typer.Option("", "--name", help="Display name."),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Connect a source. Slack/Granola resolve their ref from your token."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.add_source(
                ws, source_type, external_ref=ref or None, display_name=name or None
            )
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(f"[green]Connected[/green] {data['display_name']}  [dim]→ {data['id']}[/dim]")


@sources_app.command("sync")
def sources_sync(
    source_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Trigger an immediate re-index of a connected source you own."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.sync_source(ws, source_id)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(f"[green]Sync queued[/green]  [dim]task: {data.get('task_id')}[/dim]")


@sources_app.command("rm")
def sources_rm(
    source_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Disconnect a source you own (its indexed documents cascade away)."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.delete_source(ws, source_id)
        except CartridgeError as e:
            _err(e)
    console.print("[green]Source removed.[/green]")


@sources_app.command("browse")
def sources_browse(
    source: str = typer.Argument(..., help="A source handle from `stash sources ls`."),
    path: str = typer.Argument("", help="Path prefix (connected sources only)."),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List a source's entries like a file system."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.list_source_entries(ws, source, path=path)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if not data:
        console.print("[dim]Empty.[/dim]")
        return
    for entry in data:
        ref = entry.get("path") or entry.get("id")
        console.print(f"  [{entry.get('kind', 'file')}] {entry['name']}  [dim]({ref})[/dim]")


@sources_app.command("read")
def sources_read(
    source: str = typer.Argument(..., help="A source handle from `stash sources ls`."),
    ref: str = typer.Argument(..., help="Page id (files), session id (sessions), or doc path."),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Read one document from a source."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.read_source_doc(ws, source, ref)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(data.get("content") or data.get("transcript") or "")


@sources_app.command("search")
def sources_search(
    query: str = typer.Argument(...),
    source: str = typer.Option("", "--source", help="Scope to one source handle."),
    workspace_id: str = typer.Option(None, "--ws"),
    limit: int = typer.Option(20, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Search across sources (alias of `stash search`)."""
    _print_search(query, source, workspace_id, limit, as_json)


# ===========================================================================
# Shares — grant a person access to a folder/page/file/session by email
# ===========================================================================

shares_app = typer.Typer(help="Shares — grant people access to an object by email.")
app.add_typer(shares_app, name="shares")

_SHARE_OBJECT_TYPES = "folder | page | file | session | table"


@shares_app.command("ls")
def shares_ls(
    object_type: str = typer.Argument(..., help=_SHARE_OBJECT_TYPES),
    object_id: str = typer.Argument(...),
    as_json: bool = typer.Option(False, "--json"),
):
    """List who an object is shared with."""
    with _client() as c:
        try:
            data = c.list_object_shares(object_type, object_id)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if not data:
        console.print("[dim]Not shared with anyone.[/dim]")
        return
    for s in data:
        who = s.get("display_name") or s.get("name") or s.get("email") or s.get("principal_id")
        console.print(f"  [bold]{who}[/bold]  [dim]{s.get('permission')}[/dim]")


@shares_app.command("add")
def shares_add(
    object_type: str = typer.Argument(..., help=_SHARE_OBJECT_TYPES),
    object_id: str = typer.Argument(...),
    email: str = typer.Argument(..., help="Recipient email (pending until they sign up)."),
    permission: str = typer.Option("read", "--permission", help="read | comment | write"),
    expires: str = typer.Option(
        None, "--expires", help="ISO-8601 expiry, e.g. 2026-12-31T00:00:00Z (omit = never)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Share an object with a person by email."""
    with _client() as c:
        try:
            data = c.share_object(
                object_type, object_id, email, permission=permission, expires_at=expires or None
            )
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if data.get("pending"):
        console.print(f"[green]Invite pending[/green] for {email} (converts on signup).")
    else:
        console.print(f"[green]Shared[/green] with {email} ({permission}).")


@shares_app.command("rm")
def shares_rm(
    object_type: str = typer.Argument(..., help=_SHARE_OBJECT_TYPES),
    object_id: str = typer.Argument(...),
    principal_id: str = typer.Argument(..., help="The user id to revoke (from `shares ls`)."),
    principal_type: str = typer.Option("user", "--principal-type"),
):
    """Revoke a person's access to an object."""
    with _client() as c:
        try:
            c.unshare_object(object_type, object_id, principal_type, principal_id)
        except CartridgeError as e:
            _err(e)
    console.print("[green]Access revoked.[/green]")


# ===========================================================================
# Batch ops
# ===========================================================================

batch_app = typer.Typer(help="Batch — move/delete/restore many items at once.")
app.add_typer(batch_app, name="batch")


def _parse_batch_items(refs: list[str]) -> list[dict]:
    """Parse `type:id` tokens (e.g. page:abc file:def) into batch items."""
    items = []
    for ref in refs:
        if ":" not in ref:
            _err(f"Invalid item '{ref}' — use type:id, e.g. page:<id>")
        object_type, object_id = ref.split(":", 1)
        items.append({"object_type": object_type, "object_id": object_id})
    return items


@batch_app.command("move")
def batch_move(
    refs: list[str] = typer.Argument(..., help="Items as type:id, e.g. page:<id> file:<id>"),
    workspace_id: str = typer.Option(None, "--ws"),
    to_folder: str = typer.Option(None, "--to-folder", help="Target folder id"),
    to_root: bool = typer.Option(False, "--to-root", help="Move to the workspace root"),
):
    """Move many items (pages, files, folders, tables) at once."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            result = c.batch_move(
                ws,
                _parse_batch_items(refs),
                target_folder_id=to_folder or None,
                move_to_root=to_root,
            )
        except CartridgeError as e:
            _err(e)
    output_json(result)


@batch_app.command("delete")
def batch_delete(
    refs: list[str] = typer.Argument(..., help="Items as type:id (pages/files)"),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Move many pages/files to the trash at once."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            result = c.batch_delete(ws, _parse_batch_items(refs))
        except CartridgeError as e:
            _err(e)
    output_json(result)


@batch_app.command("restore")
def batch_restore(
    refs: list[str] = typer.Argument(..., help="Items as type:id (pages/files)"),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Restore many pages/files from the trash at once."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            result = c.batch_restore(ws, _parse_batch_items(refs))
        except CartridgeError as e:
            _err(e)
    output_json(result)


# ===========================================================================
# Trash
# ===========================================================================

trash_app = typer.Typer(help="Trash — soft-deleted pages, files, and sessions.")
app.add_typer(trash_app, name="trash")


@trash_app.command("list")
def trash_list(
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List trashed pages, files, and sessions in this workspace."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.get_trash(ws)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    for kind in ("pages", "files", "sessions"):
        items = data.get(kind, [])
        console.print(f"\n[bold]{kind.capitalize()} ({len(items)})[/bold]")
        if not items:
            console.print("  [dim]empty[/dim]")
            continue
        for item in items:
            who = item.get("deleted_by_name") or "unknown"
            console.print(
                f"  {item['id']}  {item['name']}  [dim](deleted {item['deleted_at'][:19]} by {who})[/dim]"
            )


# ===========================================================================
# Tables
# ===========================================================================

tables_app = typer.Typer(help="Tables — typed columns, rows, imports, and exports.")
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
        raise CartridgeError(
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
    c: CartridgeClient, workspace_id: str, row_data: dict, uploads: dict[str, str]
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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
        except CartridgeError as e:
            _err(e)
    console.print("[green]Table deleted.[/green]")


# ===========================================================================
# Uploaded files
# ===========================================================================


def _upload_path(c: CartridgeClient, workspace_id: str, path: str) -> dict:
    """Upload `path` to the given workspace. Returns FileResponse dict."""
    if not Path(path).is_file():
        console.print(f"[red]Not a file: {path}[/red]")
        raise typer.Exit(1)
    return c.upload_ws_file(workspace_id, path)


def _get_file_meta(c: CartridgeClient, workspace_id: str, file_id: str) -> dict:
    return c.get_ws_file(workspace_id, file_id)


@files_app.command("upload")
def files_upload(
    path: str = typer.Argument(..., help="Local file path to upload."),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Upload a file to a workspace.

    Markdown (.md/.markdown/.mdx) and HTML (.html/.htm) become editable
    pages; everything else becomes a binary file. The server does the
    routing, so the returned object's `kind` tells you what landed where.
    """
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = _upload_path(c, ws, path)
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        kind = data.get("kind", "file")
        label = "Uploaded as page" if kind == "page" else "Uploaded"
        console.print(f"[green]{label}[/green] {data['name']}  [dim]{data['id']}[/dim]")
        console.print(data["app_url"])


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
        except CartridgeError as e:
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


@files_app.command("edit-file")
def files_edit_file(
    file_id: str = typer.Argument(...),
    name: str = typer.Option(None, "--name", help="Rename the file."),
    folder: str = typer.Option(None, "--folder", help="Move into this folder id."),
    to_root: bool = typer.Option(False, "--to-root", help="Move to workspace root."),
    workspace_id: str = typer.Option(None, "--ws"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Rename and/or move a file. Pass any subset of --name / --folder / --to-root."""
    if folder and to_root:
        console.print("[red]--folder and --to-root are mutually exclusive[/red]")
        raise typer.Exit(1)
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            data = c.update_ws_file(
                ws,
                file_id,
                name=name,
                folder_id=folder,
                move_to_root=to_root,
            )
        except CartridgeError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]File updated.[/green] {data['name']}  [dim]{data['id']}[/dim]")


@files_app.command("rm")
def files_rm(
    file_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    permanent: bool = typer.Option(
        False,
        "--permanent",
        help="Trash and then immediately purge — skips the recoverable trash window.",
    ),
):
    """Move a file to trash. Pass --permanent to wipe it without going through trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.delete_ws_file(ws, file_id)
            if permanent:
                c.purge_ws_file(ws, file_id)
        except CartridgeError as e:
            _err(e)
    console.print(
        "[green]File permanently deleted.[/green]"
        if permanent
        else "[green]File moved to trash.[/green]"
    )


@files_app.command("restore")
def files_restore(
    file_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Restore a file from trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.restore_ws_file(ws, file_id)
        except CartridgeError as e:
            _err(e)
    console.print("[green]File restored.[/green]")


@files_app.command("purge")
def files_purge(
    file_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Permanently delete a file already in trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.purge_ws_file(ws, file_id)
        except CartridgeError as e:
            _err(e)
    console.print("[green]File permanently deleted.[/green]")


@files_app.command("rm-page")
def files_rm_page(
    page_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    permanent: bool = typer.Option(False, "--permanent"),
):
    """Move a page to trash. Pass --permanent to wipe it without going through trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.delete_page(ws, page_id)
            if permanent:
                c.purge_page(ws, page_id)
        except CartridgeError as e:
            _err(e)
    console.print(
        "[green]Page permanently deleted.[/green]"
        if permanent
        else "[green]Page moved to trash.[/green]"
    )


@files_app.command("restore-page")
def files_restore_page(
    page_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Restore a page from trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.restore_page(ws, page_id)
        except CartridgeError as e:
            _err(e)
    console.print("[green]Page restored.[/green]")


@files_app.command("purge-page")
def files_purge_page(
    page_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
):
    """Permanently delete a page already in trash."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            c.purge_page(ws, page_id)
        except CartridgeError as e:
            _err(e)
    console.print("[green]Page permanently deleted.[/green]")


@files_app.command("copy-page")
def files_copy_page(
    page_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    to_folder: str = typer.Option(None, "--to-folder", help="Target folder id"),
):
    """Duplicate a page as 'Copy of <name>'."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            page = c.copy_page(ws, page_id, target_folder_id=to_folder or None)
        except CartridgeError as e:
            _err(e)
    console.print(f"[green]Copied to[/green] {page['name']} ({page['id']})")


@files_app.command("copy-folder")
def files_copy_folder(
    folder_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    to_folder: str = typer.Option(None, "--to-folder", help="Target parent folder id"),
):
    """Deep-duplicate a folder as 'Copy of <name>'."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            folder = c.copy_folder(ws, folder_id, target_folder_id=to_folder or None)
        except CartridgeError as e:
            _err(e)
    console.print(f"[green]Copied to[/green] {folder['name']} ({folder['id']})")


@files_app.command("copy-file")
def files_copy_file(
    file_id: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--ws"),
    to_folder: str = typer.Option(None, "--to-folder", help="Target folder id"),
):
    """Duplicate an uploaded file as 'Copy of <name>'."""
    ws = workspace_id or _resolve_workspace()
    with _client() as c:
        try:
            f = c.copy_ws_file(ws, file_id, target_folder_id=to_folder or None)
        except CartridgeError as e:
            _err(e)
    console.print(f"[green]Copied to[/green] {f['name']} ({f['id']})")


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
        except CartridgeError as e:
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
    console.print("  [dim]3.[/dim] [cyan]cp .env.example .env[/cyan]")
    console.print(
        "  [dim]4.[/dim] edit [cyan].env[/cyan] and [cyan]Caddyfile[/cyan] for your domain"
    )
    console.print("  [dim]5.[/dim] [cyan]docker compose -f docker-compose.prod.yml up -d[/cyan]")
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


def _handle_not_member(ws_id: str) -> None:
    """Handle the case where .stash exists but the user isn't a member."""
    console.print(f"\n  This repo is connected to workspace [bold]{ws_id[:8]}…[/bold].")
    console.print("  You're not a member. Ask a workspace admin for an invite link.")


def _auto_connect_repo(repo_root: Path, cfg: dict) -> None:
    """Connect a repo to a workspace, auto-creating one named after the repo directory."""
    manifest_path = repo_root / MANIFEST_FILE

    with CartridgeClient(base_url=cfg["base_url"], api_key=cfg["api_key"]) as c:
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
            except CartridgeError as e:
                if e.status_code in (403, 404):
                    console.print(
                        f"  [yellow]Workspace {ws_id[:8]}… not found — "
                        f"replacing stale .stash[/yellow]"
                    )
                    manifest_path.unlink()
                else:
                    raise

        repo_name = repo_root.name
        my_workspaces = c.list_workspaces()
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

This repo uses [Stash](https://joinstash.ai) for shared agent sessions.
Your coding agent has the `stash` CLI on its PATH. Run `stash --help` to see commands.

**Before starting work, use Stash to check for relevant context.** When you need to understand
why something was built a certain way, what's been tried before, or what teammates are working on,
search Stash first — it has the full session record and human decisions across the team.

### What a Stash is

A Stash is a *named, curated bundle of related artifacts* (pages, files, sessions, tables) with
its own access control and an optional public URL. Use one when you're publishing a *collection*
of related things together — a project writeup with its supporting files, a research thread with
its sources, a session transcript plus the files it produced.

A Stash is **not** a wrapper to slap on every single file you happen to share. One-item Cartridges
clutter Discover and defeat the model. Pick the right tool:

- Internal share of a single file → `stash files upload <path> --json`, hand over `app_url`.
- Upload a folder/project → `stash upload <path> --json` (returns `app_url`, no Stash).
- Publishing a curated bundle → `stash upload <path> --stash "<title>" --json`.
- Composing from existing items → `stash cartridges create "<title>" --items '<json>' --json`.
- Share a coding session → `stash share <session_id>`.

Run `stash prompts agent-guidance` to reprint this rule mid-session.

### Browsing Stash

Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS:
- `stash vfs ls /`
- `stash vfs "find /workspaces -maxdepth 3 -type f"`
- `stash vfs "rg 'query' /workspaces"`
- `stash vfs "cat '/workspaces/<workspace>/README.md' | sed -n '1,80p'"`

Common reads (all support `--json`):
- `stash sessions search "<query>"` — full-text search across transcripts
- `stash sessions query --limit 20` — latest events
- `stash sessions agents` — who's been active
- `stash files pages --all` — shared pages across workspaces

Common writes:
- `stash share --title "..."` — share this session as a public Stash
- `stash read <url>` — read a public Stash URL
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
def login_cmd():
    """Authenticate with Stash. On first run, walks through full onboarding."""
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
            with CartridgeClient(base_url=base_url, api_key=cfg["api_key"]) as c:
                user = c.whoami()
            console.print(f"  [green]✓[/green] Authenticated as [bold]{user['name']}[/bold]")
        except CartridgeError:
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
        _install_all_hooks(load_enabled_agents())
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
            console.print(
                "[yellow]Not inside a git repo. Run `stash connect` from a repo.[/yellow]"
            )
        else:
            try:
                _auto_connect_repo(repo_root, cfg)
            except CartridgeError as e:
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
            except CartridgeError as e:
                console.print(f"[red]Could not connect repo: {e.detail}[/red]")

    # --- Step 6: Import historical conversations ---
    _onboarding_import_history(detected)

    _show_setup_complete_splash()


@app.command("connect")
def connect_cmd():
    """Connect this repo to a Stash workspace."""
    cfg = _require_auth()
    telemetry.record("connect")

    repo_root = _git_toplevel()
    if not repo_root:
        console.print("[red]Not inside a git repo.[/red]")
        raise typer.Exit(1)

    _auto_connect_repo(repo_root, cfg)


@app.command("join")
def join_cmd():
    """Request to join this repo's workspace."""
    _require_auth()

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
    _handle_not_member(ws_id)


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

    with CartridgeClient(base_url=cfg["base_url"], api_key=cfg["api_key"]) as c:
        try:
            c.leave_workspace(ws_id)
        except CartridgeError as e:
            if "owner" in str(e.detail).lower():
                console.print("  [red]Owners cannot leave their own workspace.[/red]")
                return
            console.print(f"  [red]{e.detail}[/red]")
            return

    clear_streaming(ws_id)
    console.print(f"  [green]✓[/green] Left workspace {ws_id[:8]}…")


def _streaming_scope(manifest: dict) -> str:
    """The on/off key for streaming: the destination folder the repo pins, else
    the workspace (its Default destination). Mirrors the plugin's _streaming_scope."""
    return manifest.get("session_folder_id") or manifest.get("workspace_id", "")


def _scope_label(manifest: dict) -> str:
    if manifest.get("session_folder_id"):
        return "this repo's session folder"
    return f"workspace {manifest.get('workspace_id', '')[:8]}… (Default folder)"


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

    with CartridgeClient(base_url=cfg["base_url"], api_key=cfg["api_key"]) as c:
        try:
            c.get_workspace(workspace_id)
        except CartridgeError as e:
            if e.status_code in (403, 404):
                console.print(
                    "  [yellow]You're not a member of this workspace.[/yellow] "
                    "Ask a workspace admin for an invite link."
                )
                return
            else:
                raise

    scope = _streaming_scope(manifest)
    set_streaming(scope)
    console.print(f"  [green]✓[/green] Streaming enabled for {_scope_label(manifest)}.")


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

    scope = _streaming_scope(manifest)
    clear_streaming(scope)
    console.print(f"  [green]✓[/green] Streaming stopped for {_scope_label(manifest)}.")


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


def _onboarding_import_history(detected_agents: list[str]) -> None:
    """Offer to import historical conversations during onboarding."""
    from .import_history import discover_conversations, summarize_discovery, upload_conversation

    agents = detected_agents or None
    conversations = discover_conversations(agents)
    if not conversations:
        return

    summary = summarize_discovery(conversations)
    console.print("\n[bold]Historical conversations found:[/bold]\n")
    for ag, info in sorted(summary.items()):
        sz = info["total_size_bytes"]
        label = f"{sz // 1024 // 1024} MB" if sz > 1024 * 1024 else f"{sz // 1024} KB"
        console.print(f"  {ag:<12} {info['count']:>4} conversations   ({label})")

    _reserve_bottom_padding(4)
    ok = questionary.confirm(
        f"Import {len(conversations)} historical conversations?", default=True
    ).ask()
    if not ok:
        return

    ws = _resolve_workspace()
    from rich.progress import Progress

    imported = 0
    errors = 0
    last_error = ""
    with _client() as c, Progress(console=console) as progress:
        task = progress.add_task("Importing…", total=len(conversations))
        for conv in conversations:
            try:
                upload_conversation(c, ws, conv, default_cartridge_id=_default_cartridge_id())
                imported += 1
            except CartridgeError as e:
                errors += 1
                last_error = str(e)
            progress.advance(task)

    console.print(f"  [green]��[/green] Imported {imported} conversations")
    if errors:
        console.print(f"  [yellow]{errors} failed — {last_error}[/yellow]")


def _setup_complete_intro(ws_url: str) -> str:
    workspace_link_section = (
        "[bold]See your workspace[/bold]   [dim](transcripts and team activity)[/dim]\n"
        f"  [link={ws_url}][bold #1e3a8a]{ws_url}[/bold #1e3a8a][/link]\n"
        "\n"
        if ws_url
        else ""
    )
    memory_section = (
        "It can read the transcripts your teammates' coding agents push to this\n"
        "workspace — so it knows what the rest of your team is working on.\n"
        "\n"
        if ws_url
        else "No repo is connected yet. Run [cyan]stash connect[/cyan] from a git repo when\n"
        "you're ready to upload transcripts to a workspace.\n"
        "\n"
    )
    team_section = (
        "[bold]Share with your team[/bold]\n"
        "Commit the [cyan].stash[/cyan] file and push. Teammates who clone the repo\n"
        "will see a prompt to run [cyan]stash start[/cyan]."
        if ws_url
        else "[bold]Connect a repo when ready[/bold]\n"
        "Run [cyan]stash connect[/cyan] from the repo you want Stash to remember."
    )
    return (
        "[bold]What just happened[/bold]\n"
        "Your coding agent now has the [bold #1e3a8a]stash[/bold #1e3a8a] CLI on its PATH.\n"
        f"{memory_section}"
        f"{workspace_link_section}"
        "[bold]Commands your agent can now use[/bold]\n"
        '  [#1e3a8a]stash vfs "find /workspaces -maxdepth 3 -type f"[/#1e3a8a]   browse Stash like a filesystem\n'
        '  [#1e3a8a]stash sessions search "<query>"[/#1e3a8a]   full-text search across transcripts\n'
        "  [#1e3a8a]stash sessions query --agent <name>[/#1e3a8a]   pull a specific agent's events\n"
        "\n"
        "Run [bold]stash --help[/bold] to see everything.\n"
        "\n"
        f"{team_section}"
    )


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
    title = "Your team's shared agent memory" if ws_url else "Stash CLI ready"
    console.print(
        Panel(
            Text.from_markup(_setup_complete_intro(ws_url)),
            title=f"[bold #1e3a8a]{title}[/bold #1e3a8a]",
            border_style="#1e3a8a",
            padding=(1, 2),
        )
    )
    console.print()

    warning = shadow_install_warning()
    if warning:
        console.print(Text(warning, style="yellow"))
        console.print()


@app.command("welcome")
def welcome_cmd():
    """Show the post-install welcome splash."""
    _show_setup_complete_splash()


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


def _upload_health_snapshot() -> list[dict]:
    agents = []
    for agent, data_dir in PLUGIN_DATA_DIRS.items():
        if not data_dir.exists():
            continue
        status = read_upload_status(data_dir)
        status["agent"] = agent
        status["label"] = _AGENT_LABEL.get(agent, agent)
        status["data_dir"] = str(data_dir)
        agents.append(status)
    return agents


def _failing_upload_agents(snapshot: list[dict]) -> list[dict]:
    failing = []
    for item in snapshot:
        if item.get("health") == "failing":
            failing.append(item)
    return failing


def _format_age(timestamp: float | int | None) -> str:
    if not timestamp:
        return "never"
    seconds = max(0, int(time.time() - float(timestamp)))
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _upload_health_label(snapshot: list[dict]) -> str:
    if not snapshot:
        return "(none detected)"
    failing = _failing_upload_agents(snapshot)
    if failing:
        labels = []
        for item in failing:
            queued = int(item.get("queued_events") or 0)
            suffix = f", {queued} queued" if queued else ""
            labels.append(f"{item['label']} failing{suffix}")
        return "; ".join(labels)
    if all(item.get("health") == "ok" for item in snapshot):
        return "ok"
    return "no upload attempts recorded yet"


@app.command("status")
def status_cmd(as_json: bool = typer.Option(False, "--json")):
    """Show local Stash upload health."""
    snapshot = _upload_health_snapshot()
    if _use_json(as_json):
        output_json({"upload_health": snapshot})
        return

    console.print("[bold]Stash upload status[/bold]\n")
    if not snapshot:
        console.print("[dim]No installed Stash agent plugins found on this machine.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Agent")
    table.add_column("Health")
    table.add_column("Queued")
    table.add_column("Last success")
    table.add_column("Last failure")
    table.add_column("Last error")

    for item in snapshot:
        health = str(item.get("health") or "unknown")
        if health == "ok":
            health_label = "[green]ok[/green]"
        elif health == "failing":
            health_label = "[red]failing[/red]"
        else:
            health_label = "[dim]unknown[/dim]"
        table.add_row(
            item["label"],
            health_label,
            str(item.get("queued_events") or 0),
            _format_age(item.get("last_success_at")),
            _format_age(item.get("last_failure_at")),
            str(item.get("last_error") or ""),
        )

    console.print(table)
    console.print("\n[dim]Status is local to this machine and updates when agent hooks run.[/dim]")


def _render_settings_header(cfg: dict) -> None:
    """Print the read-only portion of the settings page."""
    console.clear()
    console.print("[bold]Stash settings[/bold]\n")

    manifest = load_manifest()
    workspace_id = (manifest.get("workspace_id") if manifest else None) or ""
    default_cartridge_id = (manifest.get("default_cartridge_id") if manifest else None) or ""
    workspace_label = workspace_id[:12] + "…" if workspace_id else "(none — no .stash file)"
    default_cartridge_label = default_cartridge_id[:12] + "…" if default_cartridge_id else "(none)"

    def row(label: str, value: str, *, highlight: bool = True) -> None:
        console.print(f"  [dim]{label}[/dim]{value}", highlight=highlight)

    row(f"{'User:':<14}", cfg.get("username") or "(not logged in)")
    row(f"{'Workspace:':<14}", workspace_label, highlight=False)
    row(f"{'Default Stash:':<14}", default_cartridge_label, highlight=False)

    enabled = load_enabled_agents()
    detected = _detected_agents()
    if enabled is None:
        agents_label = ", ".join(_AGENT_LABEL.get(a, a) for a in detected) or "(none detected)"
    else:
        agents_label = ", ".join(_AGENT_LABEL.get(a, a) for a in enabled) or "(none)"
    row(f"{'Streaming:':<14}", agents_label)

    plugins_seen = [name for name, d in PLUGIN_DATA_DIRS.items() if d.exists()]
    row(f"{'Plugins:':<14}", ", ".join(plugins_seen) or "(none detected)")
    row(f"{'Uploads:':<14}", _upload_health_label(_upload_health_snapshot()))
    console.print()


@app.command("settings")
def settings_cmd(as_json: bool = typer.Option(False, "--json")):
    """Interactive settings page. Pass --json for a read-only snapshot."""
    cfg = load_config()

    display_cfg = dict(cfg)
    if display_cfg.get("api_key"):
        display_cfg["api_key"] = display_cfg["api_key"][:10] + "..."

    if as_json:
        output_json(
            {
                "config": display_cfg,
                "enabled_agents": load_enabled_agents(),
                "plugins_installed": [name for name, d in PLUGIN_DATA_DIRS.items() if d.exists()],
                "upload_health": _upload_health_snapshot(),
            }
        )
        return

    while True:
        cfg = load_config()
        _render_settings_header(cfg)

        base_url = cfg.get("base_url", "")
        enabled = load_enabled_agents()
        detected = _detected_agents()
        enabled_label = ", ".join(_AGENT_LABEL.get(a, a) for a in (enabled or detected)) or "(none)"

        rows = [
            ("Streaming", enabled_label, "enabled_agents"),
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
        except CartridgeError as e:
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
        except CartridgeError as e:
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


@app.command("mount", hidden=True)
def mount_command(
    mountpoint: str | None = typer.Argument(
        None,
        help="Directory where Stash should be mounted. Defaults to /Volumes/Stash on macOS.",
    ),
    workspace_id: str = typer.Option(
        None,
        "--ws",
        help="Mount one workspace by id. By default every accessible workspace is exposed.",
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help="Verify the local experimental FUSE runtime is available, then exit.",
    ),
):
    """Experimentally mount Stash as a local FUSE filesystem."""
    from .mount import CartridgeMountError, check_fuse_runtime, mount_cartridge

    telemetry.record("mount")
    if check:
        try:
            check_fuse_runtime()
        except CartridgeMountError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        console.print("[green]FUSE runtime available.[/green]")
        return

    if mountpoint is None and sys.platform == "darwin":
        mountpoint = "/Volumes/Stash"

    if mountpoint is None:
        console.print("[red]MOUNTPOINT is required unless --check is set.[/red]")
        raise typer.Exit(1)

    cfg = load_config()
    if not cfg.get("api_key"):
        console.print("[red]Not signed in. Run [bold]stash signin[/bold] first.[/red]")
        raise typer.Exit(1)

    client = CartridgeClient(base_url=cfg["base_url"], api_key=cfg["api_key"])
    try:
        console.print(f"[green]Mounting Stash at {mountpoint}[/green]")
        console.print("[dim]Press Ctrl-C to unmount.[/dim]")
        mount_cartridge(client, Path(mountpoint).expanduser(), workspace_id=workspace_id)
    except CartridgeMountError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    finally:
        client.close()


@app.command("vfs", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def vfs_command(
    ctx: typer.Context,
    workspace_id: str = typer.Option(
        None,
        "--ws",
        help="Use one workspace by id. By default every accessible workspace is exposed.",
    ),
    cwd: str = typer.Option("/", "--cwd", help="Virtual working directory."),
):
    """Run bash-shaped commands against Stash without mounting a filesystem."""
    from .app_vfs import CartridgeAppVfsShell
    from .mount import CartridgeMountError, CartridgeVfsModel

    cfg = load_config()
    if not cfg.get("api_key"):
        console.print("[red]Not signed in. Run [bold]stash signin[/bold] first.[/red]")
        raise typer.Exit(1)

    client = CartridgeClient(base_url=cfg["base_url"], api_key=cfg["api_key"])
    try:
        model = CartridgeVfsModel(client, workspace_id=workspace_id)
        model.refresh()
        shell = CartridgeAppVfsShell(model, cwd=cwd)

        command = " ".join(ctx.args).strip()
        if command:
            result = shell.run(command)
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            if result.exit_code:
                raise typer.Exit(result.exit_code)
            return

        while True:
            try:
                command = input(f"stash:{shell.cwd}$ ").strip()
            except EOFError:
                return
            if command in ("exit", "quit"):
                return
            if not command:
                continue
            result = shell.run(command)
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
    except CartridgeMountError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    finally:
        client.close()


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


@app.command("publish")
def publish_cmd(
    file_path: str = typer.Argument(..., help="Path to .html or .md file to publish"),
    title: str = typer.Option(None, "--title", "-t", help="Page title (defaults to filename)"),
    workspace_id: str = typer.Option(None, "--workspace", "-w"),
    folder_id: str = typer.Option(
        None, "--folder", "-f", help="Defaults to auto-created 'AI Drafts' folder"
    ),
    audience: str = typer.Option("public", "--audience", help="workspace | private | public"),
):
    """Publish a local file as a Stash page and print the share URL.

    Single call: creates the page, wraps it in a Stash, and prints the Stash URL.
    Mirrors what an agent does via the MCP `stash_publish_html` tool."""
    p = Path(file_path)
    if not p.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)
    content_type = "html" if p.suffix.lower() in (".html", ".htm") else "markdown"
    cfg = load_config()
    c = CartridgeClient(cfg["base_url"], cfg.get("api_key", ""))
    ws = workspace_id or (load_manifest() or {}).get("workspace_id")
    if not ws:
        console.print("[red]No workspace. Pass --workspace or run `stash connect`.[/red]")
        raise typer.Exit(1)
    result = c.publish(
        workspace_id=ws,
        title=title or p.stem,
        content=p.read_text(),
        content_type=content_type,
        audience=audience,
        folder_id=folder_id,
    )
    console.print(result["url"])


# ===========================================================================
# Skills (markdown folders containing SKILL.md frontmatter)
# ===========================================================================

skill_app = typer.Typer(help="Skills — Files folders with a SKILL.md frontmatter file.")
app.add_typer(skill_app, name="skill")


@skill_app.command("list")
def skill_list(
    workspace_id: str = typer.Argument("", help="Workspace ID; defaults to .stash."),
    as_json: bool = typer.Option(False, "--json"),
):
    """List skills in a workspace."""
    cfg = load_config()
    c = CartridgeClient(cfg["base_url"], cfg.get("api_key", ""))
    ws = workspace_id or (load_manifest() or {}).get("workspace_id")
    if not ws:
        console.print("[red]No workspace. Pass an ID or run `stash connect`.[/red]")
        raise typer.Exit(1)
    try:
        data = c._get(f"/api/v1/workspaces/{ws}/skills")
    except CartridgeError as e:
        _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        for s in data:
            console.print(
                f"  [bold]{s['name']}[/bold]  ({s['file_count']} files)  {s.get('description', '')}"
            )
        if not data:
            console.print(
                "[muted]No skills yet. `stash skill add <workspace> <folder>` to create one.[/muted]"
            )


@skill_app.command("show")
def skill_show(
    workspace_id: str = typer.Argument(...),
    name: str = typer.Argument(...),
):
    """Read a skill (SKILL.md frontmatter + body + sibling files concatenated)."""
    cfg = load_config()
    c = CartridgeClient(cfg["base_url"], cfg.get("api_key", ""))
    try:
        data = c._get(f"/api/v1/workspaces/{workspace_id}/skills/{name}")
    except CartridgeError as e:
        _err(e)
    console.print(data["combined"])


@skill_app.command("add")
def skill_add(
    workspace_id: str = typer.Argument(...),
    folder: str = typer.Argument(..., help="Local folder containing a SKILL.md file."),
):
    """Upload a local skill folder (must contain a SKILL.md) into workspace Files."""
    src = Path(folder)
    if not src.is_dir():
        console.print(f"[red]Not a folder: {folder}[/red]")
        raise typer.Exit(1)
    skill_md_path = src / "SKILL.md"
    if not skill_md_path.exists():
        console.print(f"[red]Missing SKILL.md in {folder}[/red]")
        raise typer.Exit(1)

    cfg = load_config()
    c = CartridgeClient(cfg["base_url"], cfg.get("api_key", ""))
    folder_name = src.name
    try:
        # Skills are represented as folders containing markdown pages.
        new_folder = c.create_folder(workspace_id, folder_name)
        folder_id = new_folder["id"]
        for md_file in sorted(src.glob("*.md")):
            c.create_page(
                workspace_id,
                name=md_file.name,
                content=md_file.read_text(),
                folder_id=folder_id,
                content_type="markdown",
            )
    except CartridgeError as e:
        _err(e)
    console.print(f"[green]Added skill '{folder_name}' to workspace {workspace_id}.[/green]")


# ===========================================================================
# Prompts — reusable agent-facing prompts the CLI can hand back as text
# ===========================================================================

prompts_app = typer.Typer(help="Print reusable stash agent prompts.")
app.add_typer(prompts_app, name="prompts")


# Canonical explanation of what a Stash is and when to create one. Shared
# verbatim by the SessionStart hooks, the plugin CLAUDE.md, and this command,
# so every agent surface tells the same story.
AGENT_GUIDANCE_PROMPT = """\
What a Stash is
===============

A Stash is a named, curated bundle of related workspace artifacts (pages,
files, tables, sessions) with its own access control and an optional public
URL. Use one when you're publishing a bundle of related things together — a
project writeup with its supporting files, a research thread with its
sources, a session transcript with its outputs.

When to create a Stash
----------------------

Create a Stash when:
- You're publishing a curated collection of related artifacts that belong
  together as one share.
- You want a single shareable URL with its own access control (public,
  workspace-only, or private).

Do NOT create a Stash when:
- The user just wants to share one file or page internally. Workspace
  members can already see it — give them the workspace `app_url`.
- You're emitting incidental artifacts (logs, intermediate outputs).
  Upload them with `stash files upload` and pass the `app_url` back.

Commands to reach for
---------------------

- `stash files upload <path> --json` — raw file into workspace storage,
  returns `app_url`. No Stash created. This is the default for "share this
  one file with my team."
- `stash upload <path> --json` — upload files/pages into a workspace
  folder, returns the folder's `app_url`. No Stash created.
- `stash upload <path> --stash "<title>" --json` — same as above AND
  bundle the upload into a Stash with the given title. Use only when
  you're producing a shareable bundle.
- `stash cartridges create "<title>" --items '<json>' --json` — create a
  Stash that bundles existing workspace artifacts you've already
  produced. Use this to compose a Stash from many sources.
- `stash share <session_id>` — wrap a coding session (transcript + the
  files it touched) into a Stash. Sessions are inherently a bundle, so
  this is the right unit.

Browsing Stash
--------------

Use `stash vfs` when you want to browse Stash like a filesystem without
mounting anything into the OS. It accepts bash-shaped commands over the
virtual Stash tree:

- `stash vfs ls /`
- `stash vfs "find /workspaces -maxdepth 3 -type f"`
- `stash vfs "rg 'query' /workspaces"`
- `stash vfs "cat '/workspaces/<workspace>/README.md' | sed -n '1,80p'"`

Anti-pattern: minting one Stash per file you happen to share. Cartridges
exist to group related things; one item per Stash defeats the model and
clutters Discover.
"""


@prompts_app.command("agent-guidance")
def prompts_agent_guidance():
    """Print the canonical 'what is a Stash + when to create one' prompt.

    Intended for coding agents (Claude Code, Codex, Cursor, etc.) to
    re-inject when they want to remember the model mid-session."""
    console.print(AGENT_GUIDANCE_PROMPT)


if __name__ == "__main__":
    app()
