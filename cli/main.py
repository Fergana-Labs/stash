"""Stash CLI — command-line interface for files, tables, sessions, and search."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import textwrap
import time
from pathlib import Path

import httpx
import questionary
import typer
from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from stashai.plugin.doctor import shadow_install_warning
from stashai.plugin.upload_status import read_upload_status

from . import __version__, telemetry
from .client import StashClient, StashError
from .config import (
    MANIFEST_FILE,
    PRODUCTION_BASE_URL,
    Manifest,
    load_config,
    load_enabled_agents,
    load_manifest,
    save_config,
    save_enabled_agents,
    session_link_enabled,
    set_session_link,
    start_streaming,
    stop_streaming,
    stored_base_url,
    write_manifest,
)
from .formatting import console, output_json, print_user

app = typer.Typer(
    name="stash",
    help="Stash CLI — Skills, files, tables, and sessions.",
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


def _client() -> StashClient:
    cfg = load_config()
    return StashClient(base_url=cfg["base_url"], api_key=cfg.get("api_key", ""))


def _use_json(flag: bool) -> bool:
    return flag


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

    ssh = any(os.environ.get(v) for v in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))
    opened = False if ssh else webbrowser.open(url)

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
        "[red]Timed out waiting for sign-in.[/red] "
        "Re-run [cyan]stash signin[/cyan], or set STASH_API_KEY / STASH_URL for headless use."
    )
    raise typer.Exit(1)


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
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        print_user(data)


# ===========================================================================
# Discover (public catalog of Skills)
# ===========================================================================


def _web_app_url() -> str:
    """Map the configured API base_url to the matching web app URL."""
    api = load_config().get("base_url", PRODUCTION_BASE_URL)
    if api.startswith("https://api."):
        return api.replace("https://api.", "https://app.", 1)
    if "localhost" in api or "127.0.0.1" in api:
        return "http://localhost:3000"
    return api


def _skill_url(skill: dict) -> str:
    return f"{_web_app_url()}/skills/{skill['slug']}"


@app.command("browse")
def browse(
    query: str = typer.Argument("", help="Optional search query."),
    sort: str = typer.Option("trending", "--sort", help="trending | newest | popular"),
    pick: bool = typer.Option(
        True, "--pick/--no-pick", help="Open an interactive picker (default) or print a flat list."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Browse the public Skill catalog."""
    with _client() as c:
        try:
            data = c.list_discover_skills(query=query, sort=sort)
        except StashError as e:
            _err(e)

    skills = data.get("skills", [])
    if as_json:
        output_json(skills)
        return

    if not skills:
        console.print("[yellow]No public Skills match your filters.[/yellow]")
        return

    if not pick:
        for skill in skills:
            owner = skill.get("owner_display_name") or skill.get("owner_name") or "unknown"
            console.print(
                f"[bold]{skill['title']}[/bold]  [dim]by {owner}[/dim]  "
                f"{skill['item_count']} items · {skill['view_count']} views"
            )
            if skill.get("description"):
                console.print(f"  [dim]{skill['description']}[/dim]")
        return

    choices = []
    for skill in skills:
        owner = skill.get("owner_display_name") or skill.get("owner_name") or "unknown"
        label = (
            f"{skill['title']:<32} by {owner:<14} "
            f"({skill['item_count']} items, {skill['view_count']} views)"
        )
        choices.append(questionary.Choice(label, value=skill))
    choices.append(questionary.Choice("(quit)", value=None))

    picked = questionary.select("Pick a Skill:", choices=choices).ask()
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
                    f"{picked['item_count']} items · {picked['view_count']} views",
                    "dim",
                ),
            ),
            title="Skill",
            border_style="cyan",
        )
    )

    action = questionary.select(
        "What now?",
        choices=[
            questionary.Choice("Open in browser", value="open"),
            questionary.Choice("Add to your Skills", value="add"),
            questionary.Choice("Print share URL", value="url"),
            questionary.Choice("Cancel", value=None),
        ],
    ).ask()
    if not action:
        return

    url = f"{_web_app_url()}/skills/{picked['slug']}"
    if action == "open":
        import webbrowser

        webbrowser.open(url)
        console.print(f"[green]Opened[/green] {url}")
    elif action == "url":
        console.print(url)
    elif action == "add":
        with _client() as c:
            try:
                c.fork_skill(picked["slug"])
            except StashError as e:
                _err(e)
        console.print(f"[green]Added[/green] {picked['title']} to your Skills")


# ===========================================================================
# Share — publish a session as a public Skill
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
    title: str = typer.Option("", "--title", "-t", help="Title for the shared Skill."),
    session_id: str = typer.Option(
        "", "--session", "-s", help="Session ID. Auto-detected if omitted."
    ),
    files: list[str] = typer.Option([], "--file", "-f", help="Files to attach (repeatable)."),
):
    """Share a session as a public Skill.

    Publishes a focused summary (the question + finding), the full conversation
    transcript, and any attached files as a single public Skill.
    """
    _require_auth()
    telemetry.record("share")

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
        folder = c.create_folder(page_title)
        c.create_page("Summary", content=summary_md, folder_id=folder["id"])
        c.create_page("Full Transcript", content=full_md, folder_id=folder["id"])

        for sa_label, sa_raw, _sa_path in subagent_entries:
            sa_md = _transcript_to_markdown(sa_raw)
            c.create_page(f"Subagent: {sa_label}", content=sa_md, folder_id=folder["id"])
            console.print(f"  [dim]Included subagent: {sa_label}[/dim]")

        # Upload attached files into the session folder
        for fp in files:
            p = Path(fp)
            if not p.exists():
                console.print(f"[yellow]Skipping {fp} (not found)[/yellow]")
                continue
            c.upload_file(str(p), folder_id=folder["id"])
            console.print(f"  [dim]Attached {p.name}[/dim]")

        # Upload the full transcript blob (may already exist via hooks — that's fine)
        try:
            c.upload_transcript(
                sid, str(jsonl_path), agent_name="claude", cwd=str(jsonl_path.parent)
            )
        except StashError as e:
            if e.status_code != 409:
                raise

        for sa_label, _sa_raw, sa_path in subagent_entries:
            sa_session_id = Path(sa_path).stem
            try:
                c.upload_transcript(
                    sa_session_id,
                    sa_path,
                    agent_name="claude-subagent",
                    cwd=str(jsonl_path.parent),
                )
            except StashError as e:
                if e.status_code != 409:
                    raise

        # Publish the session folder so the anonymous URL works immediately.
        skill = c.publish_skill_folder(
            folder["id"],
            title=page_title,
            description="Shared session Skill",
        )

    public_url = f"{_web_app_url()}/skills/{skill['slug']}"
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
    c: StashClient,
    root_folder_id: str,
    folder_cache: dict[tuple[str, str], str],
    relative_path: Path,
) -> str:
    parent_id = root_folder_id
    for folder_name in relative_path.parts[:-1]:
        key = (parent_id, folder_name)
        if key not in folder_cache:
            folder_cache[key] = c.create_folder(
                folder_name,
                parent_folder_id=parent_id,
            )["id"]
        parent_id = folder_cache[key]
    return parent_id


@app.command("upload")
def upload(
    path: str = typer.Argument(..., help="Directory or file to upload."),
    name: str = typer.Option("", "--name", "-n", help="Name for the uploaded folder."),
    skill: str = typer.Option(
        "",
        "--skill",
        help=(
            "Also bundle the upload into a new Skill with this title. Omit "
            "for a plain upload (the common case)."
        ),
    ),
    public: bool = typer.Option(
        True,
        "--public/--private",
        help="Skill visibility (only meaningful with --skill).",
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Upload a local file or directory into your Files.

    A single file lands directly in your Files (Markdown/HTML become
    editable pages, everything else a binary file) and the returned
    ``app_url`` is the share link. A directory becomes a folder, and
    every text file in it — Markdown, HTML, code, CSV, and friends —
    becomes an editable page. **No Skill is created.**

    Pass ``--skill <title>`` to *also* bundle the upload into a shareable
    Skill. Use a Skill when you're publishing a folder of related
    artifacts (a project writeup with its supporting files, a research
    thread with its sources) — not as a wrapper around every single
    upload."""
    _require_auth()
    telemetry.record("upload")
    target = Path(path)
    if not target.exists():
        console.print(f"[red]Not found: {path}[/red]")
        raise typer.Exit(1)

    # A single file with no Skill goes straight into Files — no wrapping
    # folder. The server routes Markdown/HTML to pages.
    if target.is_file() and not skill:
        with _client() as c:
            try:
                data = _upload_path(c, str(target))
            except StashError as e:
                _err(e)
        if _use_json(as_json):
            output_json(data)
            return
        label = "Uploaded as page" if data.get("kind") == "page" else "Uploaded"
        console.print(f"[green]{label}[/green] {data['name']}  [dim]{data['id']}[/dim]")
        console.print(data["app_url"])
        return

    files = _upload_file_list(target)
    if not files:
        console.print(f"[red]No files found in {path}[/red]")
        raise typer.Exit(1)

    root_name = name or (target.stem if target.is_file() else target.name)
    skill_title = skill.strip() or root_name
    create_skill = bool(skill)
    console.print(f"[dim]Uploading {len(files)} file(s) as '{root_name}'...[/dim]")

    with _client() as c:
        root_folder = c.create_folder(root_name)
        folder_cache: dict[tuple[str, str], str] = {}

        for file_path in files:
            relative_path = (
                file_path.relative_to(target) if target.is_dir() else Path(file_path.name)
            )
            folder_id = _upload_folder_for_file(
                c,
                root_folder["id"],
                folder_cache,
                relative_path,
            )

            if _is_upload_text_file(file_path):
                content = file_path.read_text(errors="replace")
                c.create_page(file_path.name, content=content, folder_id=folder_id)
                console.print(f"  [dim]Page: {relative_path}[/dim]")
                continue

            # Creating the stub page embeds the binary: the server claims any
            # root file whose download link appears in a saved page body.
            uploaded = c.upload_file(str(file_path))
            c.create_page(
                file_path.name,
                content=_markdown_snippet(uploaded),
                folder_id=folder_id,
            )
            console.print(f"  [dim]File: {relative_path}[/dim]")

        folder_url = f"{_web_app_url()}/folders/{root_folder['id']}"
        result: dict = {"folder": root_folder, "app_url": folder_url}

        if create_skill:
            # A skill is a folder with a SKILL.md; publishing makes it public.
            try:
                c.create_page(
                    name="SKILL.md",
                    content=f"---\nname: {skill_title}\ndescription: Uploaded from {target.name}\n---\n\n# {skill_title}\n",
                    folder_id=root_folder["id"],
                    content_type="markdown",
                )
            except StashError as e:
                if e.status_code != 409:
                    raise
            if public:
                skill_row = c.publish_skill_folder(
                    root_folder["id"],
                    title=skill_title,
                    description=f"Uploaded from {target.name}",
                )
                result["skill"] = skill_row
                result["url"] = _skill_url(skill_row)
            else:
                result["url"] = folder_url

    if _use_json(as_json):
        output_json(result)
        return
    if create_skill and "skill" in result:
        console.print(
            f"\n[green bold]Uploaded![/green bold]  {result['url']}\n"
            f"[dim]Folder: {root_folder['id']}  Skill: {result['skill']['id']}[/dim]"
        )
    elif create_skill:
        console.print(
            f"\n[green bold]Uploaded![/green bold]  {folder_url}\n"
            f"[dim]Folder: {root_folder['id']}  (private skill — publish with "
            f"`stash skills publish {root_folder['id']}`)[/dim]"
        )
    else:
        console.print(
            f"\n[green bold]Uploaded![/green bold]  {folder_url}\n"
            f"[dim]Folder: {root_folder['id']}  "
            f"(pass --skill <title> to turn the folder into a shareable Skill)[/dim]"
        )


@app.command("export")
def export(
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Path for the zip (default: stash-export-<timestamp>.zip in the current directory).",
    ),
):
    """Download your entire Stash as a zip of standard files.

    Folders become directories, pages become plain .md/.html files, and
    uploads keep their original bytes — no proprietary formats, no lock-in."""
    _require_auth()
    telemetry.record("export")
    destination = (
        Path(output) if output else Path(f"stash-export-{time.strftime('%Y%m%d-%H%M%S')}.zip")
    )
    console.print("[dim]Packaging your Stash…[/dim]")
    with _client() as c:
        try:
            data = c.export_zip()
        except StashError as e:
            _err(e)
    destination.write_bytes(data)
    console.print(
        f"[green bold]Exported![/green bold]  {destination}  [dim]{len(data):,} bytes[/dim]"
    )


def _parse_skill_slug(url_or_slug: str) -> str:
    """Extract a Skill slug from a full URL or bare slug."""
    url_or_slug = url_or_slug.strip().rstrip("/")
    if "/skills/" in url_or_slug:
        return url_or_slug.split("/skills/")[-1]
    return url_or_slug


@app.command("read")
def read_skill(
    url: str = typer.Argument(..., help="Skill URL or slug."),
):
    """Read a public Skill and print its contents."""
    slug = _parse_skill_slug(url)
    with _client() as c:
        text = c.get_skill_text(slug)
    console.print(text)


# ===========================================================================
# Skills
# ===========================================================================

skills_app = typer.Typer(
    help=(
        "Skills — modules of agent-usable knowledge. Local skills are Files "
        "folders with a SKILL.md; shared skills are publishable bundles of "
        "pages, sessions, tables, and files."
    )
)
app.add_typer(skills_app, name="skills")


@skills_app.command("add")
def skills_add(
    folder: str = typer.Argument(..., help="Local folder containing a SKILL.md file."),
):
    """Upload a local skill folder (must contain a SKILL.md) into your Files."""
    src = Path(folder)
    if not src.is_dir():
        console.print(f"[red]Not a folder: {folder}[/red]")
        raise typer.Exit(1)
    skill_md_path = src / "SKILL.md"
    if not skill_md_path.exists():
        console.print(f"[red]Missing SKILL.md in {folder}[/red]")
        raise typer.Exit(1)

    folder_name = src.name
    with _client() as c:
        try:
            # Skills are represented as folders containing markdown pages.
            new_folder = c.create_folder(folder_name)
            folder_id = new_folder["id"]
            for md_file in sorted(src.glob("*.md")):
                c.create_page(
                    name=md_file.name,
                    content=md_file.read_text(),
                    folder_id=folder_id,
                    content_type="markdown",
                )
        except StashError as e:
            _err(e)
    console.print(f"[green]Added skill '{folder_name}' to your Files.[/green]")


@skills_app.command("create")
def skills_create(
    name: str = typer.Argument(..., help="Skill name (becomes the folder name)."),
    description: str = typer.Option("", "--description"),
    public: bool = typer.Option(False, "--public", help="Publish immediately."),
    discover: bool = typer.Option(False, "--discover", help="List the public Skill in Discover."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a skill: a folder with a SKILL.md template. Pass --public to publish."""
    if discover and not public:
        console.print("[red]--discover requires --public.[/red]")
        raise typer.Exit(1)
    skill_md = f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"
    with _client() as c:
        try:
            folder = c.create_folder(name)
            c.create_page(
                name="SKILL.md",
                content=skill_md,
                folder_id=folder["id"],
                content_type="markdown",
            )
            skill = None
            if public:
                skill = c.publish_skill_folder(
                    folder["id"],
                    discoverable=discover,
                )
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"folder_id": folder["id"], "name": name, "published": skill})
        return
    console.print(f"[green]Created skill[/green] '{name}'  folder {folder['id']}")
    if skill:
        console.print(f"  Public URL: [cyan]{_web_app_url()}/skills/{skill['slug']}[/cyan]")


@skills_app.command("publish")
def skills_publish(
    folder_id: str = typer.Argument(..., help="Skill folder ID to publish."),
    discover: bool = typer.Option(False, "--discover", help="List the public Skill in Discover."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Publish a skill folder: mint its share record and print the public URL."""
    with _client() as c:
        try:
            skill = c.publish_skill_folder(
                folder_id,
                discoverable=discover,
            )
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(skill)
        return
    label = "Published to Discover" if skill.get("discoverable") else "Published"
    console.print(
        f"[green]{label}[/green] '{skill['title']}' -> "
        f"[cyan]{_web_app_url()}/skills/{skill['slug']}[/cyan]"
    )


@skills_app.command("update")
def skills_update(
    skill_id: str = typer.Argument(...),
    title: str | None = typer.Option(None, "--title"),
    description: str | None = typer.Option(None, "--description"),
    discover: bool | None = typer.Option(
        None,
        "--discover/--no-discover",
        help="Whether a public Skill appears in Discover.",
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Update a published skill's metadata, access, or Discover flag."""
    fields = {}
    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = description
    if discover is not None:
        fields["discoverable"] = discover
    if not fields:
        console.print("[red]Pass at least one field to update.[/red]")
        raise typer.Exit(1)

    with _client() as c:
        try:
            skill = c.update_skill(skill_id, **fields)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(skill)
        return
    flag = f"[cyan]{skill['access']}[/cyan]"
    if skill.get("discoverable"):
        flag = f"{flag} [cyan]discover[/cyan]"
    console.print(f"[green]Updated Skill[/green] '{skill['title']}'  {flag}")


@skills_app.command("unpublish")
def skills_unpublish(skill_id: str = typer.Argument(...)):
    """Stop sharing a skill: delete its publish record. The folder stays."""
    with _client() as c:
        try:
            c.unpublish_skill(skill_id)
        except StashError as e:
            _err(e)
    console.print(f"[green]Unpublished Skill[/green] {skill_id}")


def _safe_skill_dirname(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-() ]+", "-", name).strip(" .")
    return cleaned or "skill"


def _materialize_skill(detail: dict, skills_root: Path, fetch_bytes) -> tuple[Path, int]:
    """Write a public-skill payload to skills_root/<folder_name>.

    Returns (target_dir, items_written). fetch_bytes(url) -> bytes is
    injected so tests don't hit the network. Replacing an existing install
    is allowed only when the target already looks like a skill (has a
    SKILL.md) — never delete an arbitrary directory on a name collision."""
    contents = detail["contents"]
    target = skills_root / _safe_skill_dirname(detail["folder_name"])
    if target.exists():
        if not (target / "SKILL.md").exists():
            console.print(
                f"[red]Error:[/red] {target} exists and is not a skill folder; not overwriting."
            )
            raise typer.Exit(1)
        shutil.rmtree(target)
    target.mkdir(parents=True)

    written = 0
    for page in contents["pages"]:
        name = page["name"]
        if "." not in name:
            name += ".md" if page["content_type"] == "markdown" else ".html"
        is_md = page["content_type"] == "markdown"
        body = (page["content_markdown"] if is_md else page["content_html"]) or ""
        path = target.joinpath(*page["folder_path"], name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        written += 1
    for f in contents["files"]:
        if not f.get("url"):
            console.print(f"[yellow]skipped[/yellow] {f['name']} (no download URL)")
            continue
        path = target.joinpath(*f["folder_path"], f["name"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch_bytes(f["url"]))
        written += 1
    if contents["tables"]:
        console.print(
            f"[yellow]skipped[/yellow] {len(contents['tables'])} table(s) — "
            "tables don't materialize as local skill files"
        )
    return target, written


@skills_app.command("install")
def skills_install(
    slug: str = typer.Argument(..., help="Public slug, e.g. from app.joinstash.ai/skills/<slug>."),
    directory: str = typer.Option("", "--dir", help="Skills directory to install into."),
    project: bool = typer.Option(
        False, "--project", help="Install into ./.claude/skills (this repo only)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Install a public Skill into the local agent's skills directory.

    Claude Code loads every SKILL.md folder under ~/.claude/skills (or the
    repo's .claude/skills with --project) at session start, so the Skill is
    available to the agent from its next session. Re-running updates the
    installed copy in place.
    """
    if directory and project:
        console.print("[red]Error:[/red] pass either --dir or --project, not both.")
        raise typer.Exit(1)
    if directory:
        root = Path(directory).expanduser()
    elif project:
        root = Path(".claude") / "skills"
    else:
        root = Path.home() / ".claude" / "skills"

    with _client() as c:
        try:
            detail = c.get_public_skill(slug)
        except StashError as e:
            _err(e)

    def fetch_bytes(url: str) -> bytes:
        resp = httpx.get(url, follow_redirects=True, timeout=60)
        resp.raise_for_status()
        return resp.content

    target, written = _materialize_skill(detail, root, fetch_bytes)
    if _use_json(as_json):
        output_json({"path": str(target), "items": written})
        return
    console.print(
        f"[green]Installed[/green] '{detail['skill']['title']}' → {target}  ({written} items)"
    )
    console.print("[dim]The agent loads it at its next session start.[/dim]")


# --- skills sync: two-way local <-> Stash skill sync ---

_SYNC_STATE_DIR = Path.home() / ".stash" / "skills_sync"


def _sync_state_path(root: Path) -> Path:
    # One state file per local root: the user's skills can sync to both
    # ~/.claude/skills and a repo's .claude/skills independently.
    root_key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:8]
    return _SYNC_STATE_DIR / f"{root_key}.json"


def _local_skill_dirs(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    return {p.name: p for p in sorted(root.iterdir()) if p.is_dir() and (p / "SKILL.md").exists()}


def _collect_local_files(skill_dir: Path) -> list[tuple[str, bytes]]:
    out = []
    for path in sorted(skill_dir.rglob("*")):
        rel = path.relative_to(skill_dir)
        if path.is_file() and not any(part.startswith(".") for part in rel.parts):
            out.append((rel.as_posix(), path.read_bytes()))
    return out


def _hash_local_skill(skill_dir: Path) -> str:
    h = hashlib.sha256()
    for rel, blob in _collect_local_files(skill_dir):
        h.update(rel.encode())
        h.update(b"\0")
        h.update(blob)
        h.update(b"\0")
    return h.hexdigest()


def _hash_remote_contents(contents: dict) -> str:
    """Change fingerprint for a skill's cloud contents. Pages hash their
    bodies; binaries hash name+size (bytes live behind presigned URLs)."""
    entries = []
    for p in contents["pages"]:
        name = p["name"]
        if "." not in name:
            name += ".md" if p["content_type"] == "markdown" else ".html"
        is_md = p["content_type"] == "markdown"
        body = (p["content_markdown"] if is_md else p["content_html"]) or ""
        sig = hashlib.sha256(body.encode()).hexdigest()
        entries.append(("/".join([*p["folder_path"], name]), sig))
    for f in contents["files"]:
        entries.append(("/".join([*f["folder_path"], f["name"]]), f"size:{f['size_bytes']}"))
    h = hashlib.sha256()
    for rel, sig in sorted(entries):
        h.update(rel.encode())
        h.update(b"\0")
        h.update(sig.encode())
        h.update(b"\0")
    return h.hexdigest()


def _sync_skills(c, root: Path, state: dict, push_new: bool, fetch_bytes) -> tuple[dict, dict]:
    """Three-way sync between root and your skills.

    state maps skill folder name -> {folder_id, local_hash, remote_hash}
    captured at the last sync; comparing each side against it tells us which
    side moved. Both moved -> conflict, skipped loudly. Returns
    (summary, new_state)."""
    remote: dict[str, dict] = {}
    for s in c.list_skills():
        detail = c.get_skill_contents(s["folder_id"])
        remote[detail["folder_name"]] = detail

    local = _local_skill_dirs(root)
    summary: dict = {"pulled": [], "pushed": [], "conflicts": [], "ignored": [], "unchanged": []}
    new_state: dict = {}

    def record(name: str, detail: dict) -> None:
        new_state[name] = {
            "folder_id": detail["folder_id"],
            "local_hash": _hash_local_skill(root / name),
            "remote_hash": _hash_remote_contents(detail["contents"]),
        }

    def pull(name: str, detail: dict) -> None:
        target, _written = _materialize_skill(
            {"folder_name": detail["folder_name"], "contents": detail["contents"]},
            root,
            fetch_bytes,
        )
        new_state[name] = {
            "folder_id": detail["folder_id"],
            "local_hash": _hash_local_skill(target),
            "remote_hash": _hash_remote_contents(detail["contents"]),
        }
        summary["pulled"].append(name)

    def push(name: str, folder_id: str) -> None:
        c.replace_skill_contents(folder_id, _collect_local_files(local[name]))
        record(name, c.get_skill_contents(folder_id))
        summary["pushed"].append(name)

    for name in sorted(set(remote) | set(local)):
        rec = state.get(name)
        detail = remote.get(name)
        try:
            if detail and name not in local:
                # The cloud is the source of truth for what exists: a tracked
                # local deletion gets re-pulled; remove skills in Stash.
                pull(name, detail)
            elif name in local and not detail:
                if rec:
                    summary["ignored"].append(f"{name} (deleted in Stash; kept local copy)")
                elif push_new:
                    folder = c.create_folder(name)
                    push(name, folder["id"])
                else:
                    summary["ignored"].append(f"{name} (local-only; `stash skills add` to share)")
            elif rec is None:
                summary["conflicts"].append(
                    f"{name} (exists on both sides but was never synced; "
                    "rename one or delete the local copy to adopt the Stash copy)"
                )
            else:
                local_changed = _hash_local_skill(local[name]) != rec["local_hash"]
                remote_changed = _hash_remote_contents(detail["contents"]) != rec["remote_hash"]
                if local_changed and remote_changed:
                    new_state[name] = rec
                    summary["conflicts"].append(f"{name} (changed locally AND in Stash)")
                elif local_changed:
                    push(name, detail["folder_id"])
                elif remote_changed:
                    pull(name, detail)
                else:
                    new_state[name] = rec
                    summary["unchanged"].append(name)
        except StashError as e:
            summary["conflicts"].append(f"{name} (sync failed: {e.detail})")
            if rec:
                new_state[name] = rec
    return summary, new_state


@skills_app.command("sync")
def skills_sync(
    directory: str = typer.Option("", "--dir", help="Skills directory to sync."),
    project: bool = typer.Option(
        False, "--project", help="Sync ./.claude/skills and push new local skills too."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Two-way sync between the local skills directory and your Skills.

    Every Skill is materialized under ~/.claude/skills (so agents load it
    next session), and local edits to synced skills are pushed back. New
    local skills are pushed only in --project mode — the global skills dir
    holds personal skills; share one deliberately with `stash skills add`.
    Skills changed on both sides are skipped loudly: resolve, then re-run.
    """
    if directory and project:
        console.print("[red]Error:[/red] pass either --dir or --project, not both.")
        raise typer.Exit(1)
    if directory:
        root = Path(directory).expanduser()
    elif project:
        root = Path(".claude") / "skills"
    else:
        root = Path.home() / ".claude" / "skills"

    state_path = _sync_state_path(root)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    def fetch_bytes(url: str) -> bytes:
        resp = httpx.get(url, follow_redirects=True, timeout=60)
        resp.raise_for_status()
        return resp.content

    with _client() as c:
        try:
            summary, new_state = _sync_skills(
                c, root, state, push_new=project, fetch_bytes=fetch_bytes
            )
        except StashError as e:
            _err(e)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, indent=1))

    if _use_json(as_json):
        output_json(summary)
        return
    for name in summary["pulled"]:
        console.print(f"[green]pulled[/green]  {name}")
    for name in summary["pushed"]:
        console.print(f"[green]pushed[/green]  {name}")
    for note in summary["ignored"]:
        console.print(f"[dim]ignored[/dim]  {note}")
    for note in summary["conflicts"]:
        console.print(f"[yellow]conflict[/yellow] {note}")
    console.print(
        f"[dim]{len(summary['pulled'])} pulled, {len(summary['pushed'])} pushed, "
        f"{len(summary['unchanged'])} unchanged, {len(summary['conflicts'])} conflicts → {root}[/dim]"
    )


@skills_app.command("fork")
def skills_fork(
    slug: str = typer.Argument(..., help="Public slug of the Skill."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Fork a public Skill into your own Skills."""
    with _client() as c:
        try:
            skill = c.fork_skill(slug)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(skill)
        return
    console.print(f"[green]Forked Skill[/green] '{skill['name']}'  folder {skill['folder_id']}")


@skills_app.command("snapshot-source")
def skills_snapshot_source(
    skill_id: str = typer.Argument(...),
    source: str = typer.Option(
        ..., "--source", help="Connected-source handle (see /sources via `stash vfs`)."
    ),
    path: str = typer.Option(..., "--path", help="Document path within the source."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Snapshot one connected-source document into a Skill as a page."""
    with _client() as c:
        try:
            data = c.snapshot_source_into_skill(skill_id, source, path)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(f"[green]Snapshotted[/green] {path}  [dim]→ page {data.get('id')}[/dim]")


# ===========================================================================
# Files: folders (nestable) + pages
# ===========================================================================

files_app = typer.Typer(help="Files — folders, pages, and uploaded files.")
app.add_typer(files_app, name="files")


@files_app.command("create-folder")
def files_create_folder(
    name: str = typer.Argument(...),
    parent: str = typer.Option(None, "--parent", help="parent folder id (omit for root)"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a folder. Omit --parent to create at the root."""
    with _client() as c:
        try:
            data = c.create_folder(name, parent_folder_id=parent)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Folder '{data['name']}' created.[/green]  ID: {data['id']}")


@files_app.command("edit-folder")
def files_edit_folder(
    folder_id: str = typer.Argument(...),
    name: str = typer.Option(..., "--name", help="New folder name."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Rename a folder. Use `stash mv` to relocate it."""
    with _client() as c:
        try:
            data = c.update_folder(folder_id, name=name)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Folder renamed.[/green] {data['name']}  [dim]{data['id']}[/dim]")


def _markdown_snippet(file_resp: dict) -> str:
    """Build an image or link markdown snippet from an uploaded FileResponse.
    Uses the stable download route — presigned storage URLs expire within
    the hour and would leave the page with dead links."""
    name = file_resp["name"]
    url = f"/api/v1/me/files/{file_resp['id']}/download"
    ct = file_resp.get("content_type", "") or ""
    if ct.startswith("image/"):
        return f"![{name}]({url})"
    return f"[{name}]({url})"


def _prepend_attachments(c: StashClient, content: str, attach: list[str] | None) -> str:
    """Upload each file and prepend its embed snippet. Saving the page body
    embeds the files server-side — no explicit attach step exists."""
    if not attach:
        return content
    block = "\n\n".join(_markdown_snippet(c.upload_file(p)) for p in attach)
    return f"{block}\n\n{content}" if content else block


@files_app.command("add-page")
def files_add_page(
    name: str = typer.Argument(...),
    folder: str = typer.Option(None, "--folder", help="folder id; omit for root"),
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
        help="HTML layout: 'responsive' (default), 'full-width' for full-window web pages, "
        "or 'fixed-aspect' for 16:9 slide decks.",
        case_sensitive=False,
    ),
    attach: list[str] = typer.Option(
        None, "--attach", help="Local file path to upload and embed (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a page. --folder drops it into a folder, otherwise it goes to the root."""
    page_type = page_type.lower()
    if page_type not in ("markdown", "html"):
        console.print(f"[red]--type must be 'markdown' or 'html', got: {page_type}[/red]")
        raise typer.Exit(1)
    if layout is not None:
        layout = layout.lower()
        if layout not in ("responsive", "fixed-aspect", "full-width"):
            console.print(
                f"[red]--layout must be 'responsive', 'fixed-aspect', or 'full-width', "
                f"got: {layout}[/red]"
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
            for p in attach or []:
                if not Path(p).is_file():
                    console.print(f"[red]Not a file: {p}[/red]")
                    raise typer.Exit(1)
            if page_type == "markdown":
                body = _prepend_attachments(c, content, attach)
            else:
                body = ""
                if attach:
                    console.print("[yellow]--attach is ignored for html pages[/yellow]")
            data = c.create_page(
                name,
                content=body,
                folder_id=folder,
                content_type=page_type,
                content_html=html_body,
                html_layout=layout,
            )
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(
            f"[green]Page '{data['name']}' created.[/green]  ID: {data['id']}  "
            f"Type: {data.get('content_type', 'markdown')}"
        )


@files_app.command("edit-page")
def files_edit_page(
    page_id: str = typer.Argument(...),
    content: str = typer.Option(None, "--content"),
    name: str = typer.Option(None, "--name"),
    page_type: str = typer.Option(
        None, "--type", help="Switch the page to this type: markdown or html.", case_sensitive=False
    ),
    html_file: str = typer.Option(
        None, "--html-file", help="Local HTML file to load as content_html."
    ),
    layout: str = typer.Option(
        None,
        "--layout",
        help="Switch HTML layout: 'responsive', 'full-width' (full-window web pages), "
        "or 'fixed-aspect' (16:9 slide decks).",
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
        if layout not in ("responsive", "fixed-aspect", "full-width"):
            console.print(
                f"[red]--layout must be 'responsive', 'fixed-aspect', or 'full-width', "
                f"got: {layout}[/red]"
            )
            raise typer.Exit(1)
    if html_body is not None and page_type is None:
        page_type = "html"
    if page_type == "html" and html_body is None and content is not None:
        html_body = content
        content = None

    with _client() as c:
        try:
            for p in attach or []:
                if not Path(p).is_file():
                    console.print(f"[red]Not a file: {p}[/red]")
                    raise typer.Exit(1)
            if attach and page_type != "html":
                base = (
                    content
                    if content is not None
                    else c.get_page(page_id).get("content_markdown", "")
                )
                content = _prepend_attachments(c, base, attach)
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
            data = c.update_page(page_id, **kwargs)
        except StashError as e:
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
    limit: int = typer.Option(20, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Sessions — agent transcripts and event logs."""
    if ctx.invoked_subcommand is not None:
        return
    with _client() as c:
        try:
            data = c.query_events(limit=limit)
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


@hist_app.command("agents")
def hist_agents(as_json: bool = typer.Option(False, "--json")):
    """List distinct agent names that have logged events."""
    with _client() as c:
        try:
            data = c.list_agent_names()
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


@hist_app.command("folders")
def hist_folders(as_json: bool = typer.Option(False, "--json")):
    """List session folders (shareable groupings of sessions)."""
    with _client() as c:
        try:
            data = c.list_session_folders()
        except StashError as e:
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a session folder."""
    with _client() as c:
        try:
            data = c.create_session_folder(name)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(f"[green]Created folder[/green] {name}  [dim]({data.get('id')})[/dim]")


@hist_app.command("use-folder")
def hist_use_folder(
    folder: str = typer.Argument(
        None, help="Folder name or id to pin this repo's sessions to. A new name is created."
    ),
    use_default: bool = typer.Option(
        False, "--default", help="Clear the pin so sessions land in the Default folder."
    ),
):
    """Pin this repo's agent sessions to a session folder (writes `.stash`)."""
    if load_manifest() is None:
        console.print(f"[red]No {MANIFEST_FILE} here. Run [bold]stash connect[/bold] first.[/red]")
        raise typer.Exit(1)
    if not folder and not use_default:
        console.print("[red]Pass a folder name/id, or --default to clear the pin.[/red]")
        raise typer.Exit(1)

    if use_default:
        write_manifest({"session_folder_id": ""})
        console.print("[green]✓[/green] Sessions will land in the Default folder.")
        return

    with _client() as c:
        try:
            folders = c.list_session_folders()
            match = next((f for f in folders if folder in (f.get("id"), f.get("name"))), None)
            if match is None:
                match = c.create_session_folder(folder)
                console.print(f"[green]Created folder[/green] {folder}")
        except StashError as e:
            _err(e)

    write_manifest({"session_folder_id": match["id"]})
    console.print(
        f"[green]✓[/green] Sessions in this repo now land in "
        f"[bold]{match.get('name')}[/bold]  [dim]({match['id']})[/dim]"
    )


@hist_app.command("push")
def hist_push(
    content: str = typer.Argument(...),
    agent_name: str = typer.Option("cli", "--agent"),
    event_type: str = typer.Option("message", "--type"),
    session_id: str = typer.Option(..., "--session"),
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
    """Push an event to your session stream."""
    telemetry.record("history.push")
    with _client() as c:
        try:
            attachments: list[dict] = []
            for path in attach or []:
                f = _upload_path(c, path)
                attachments.append(
                    {"file_id": f["id"], "name": f["name"], "content_type": f["content_type"]}
                )
            for fid in attach_id or []:
                f = _get_file_meta(c, fid)
                attachments.append(
                    {"file_id": f["id"], "name": f["name"], "content_type": f["content_type"]}
                )
            data = c.push_event(
                agent_name=agent_name,
                event_type=event_type,
                content=content,
                session_id=session_id,
                tool_name=tool_name,
                attachments=attachments or None,
                created_at=created_at,
            )
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Event recorded.[/green]  ID: {data['id']}")


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


@hist_app.command("import")
def hist_import(
    agent_name: str = typer.Option(None, "--agent", help="Only import from this agent."),
    limit: int = typer.Option(0, "-n", "--limit", help="Max conversations to import (0 = all)."),
    replace: bool = typer.Option(False, "--replace", help="Replace sessions that already exist."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Import historical conversations from coding agents on this machine.

    Discovers conversations from Claude Code, Cursor, and Codex, then uploads
    them as transcripts.
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
        ok = questionary.confirm(f"Import {len(conversations)} conversations?", default=True).ask()
        if not ok:
            raise typer.Exit(0)

    from rich.progress import Progress

    imported = 0
    errors = 0
    with _client() as c, Progress(console=console) as progress:
        task = progress.add_task("Importing…", total=len(conversations))
        for conv in conversations:
            try:
                upload_conversation(
                    c,
                    conv,
                    replace=replace,
                )
                imported += 1
            except (StashError, httpx.HTTPError):
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


# ===========================================================================
# Cloud agents — chat turns executing on your cloud computer
# ===========================================================================

agent_app = typer.Typer(
    help="Cloud agents — start, monitor, and stop agent turns on your cloud computer."
)
app.add_typer(agent_app, name="agent")


def _resolve_agent_id(c: StashClient, ref: str) -> str:
    """An agent id or (case-insensitive) name → its id."""
    agents = c.list_agents()
    matches = [a for a in agents if ref in (a["id"], a["name"]) or a["name"].lower() == ref.lower()]
    if not matches:
        console.print(f"[red]No agent named '{ref}'. See [bold]stash agent list[/bold].[/red]")
        raise typer.Exit(1)
    if len(matches) > 1:
        console.print(f"[red]'{ref}' matches multiple agents — pass an id instead.[/red]")
        raise typer.Exit(1)
    return matches[0]["id"]


def _render_tool_event(event: dict) -> str:
    name = event.get("name") or "tool"
    args = event.get("args") or {}
    if name == "Bash" and args.get("command"):
        return f"⚙ Ran: {str(args['command'])[:200]}"
    if args.get("file_path"):
        return f"⚙ {name} {args['file_path']}"
    return f"⚙ {name}"


def _stream_turn(events) -> str | None:
    """Render a turn's SSE events live; returns the session id (chat streams
    open with a session event; run streams don't carry one)."""
    session_id: str | None = None
    for event in events:
        kind = event.get("type")
        if kind == "session":
            session_id = event["session_id"]
        elif kind == "status":
            console.print(f"[dim]· {event.get('stage', 'working')}…[/dim]")
        elif kind == "text":
            print(event.get("delta", ""), end="", flush=True)
        elif kind == "tool":
            console.print(f"\n[dim]{_render_tool_event(event)}[/dim]")
        elif kind == "error":
            console.print(f"\n[red]Error: {event.get('message')}[/red]")
        elif kind == "end":
            print()
    return session_id


@agent_app.command("list")
def agent_list(as_json: bool = typer.Option(False, "--json")):
    """List your configured agents (personas, models, schedules)."""
    with _client() as c:
        try:
            agents = c.list_agents()
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(agents)
        return
    for a in agents:
        schedule = f"  cron {a['schedule_cron']}" if a.get("schedule_cron") else ""
        model = a.get("model_provider") or "auto"
        console.print(
            f"  [bold]{a['name']}[/bold]  [dim]{a['run_mode']}  {model}{schedule}  ({a['id']})[/dim]"
        )


@agent_app.command("chat")
def agent_chat(
    message: str = typer.Argument(..., help="The message to send."),
    session: str = typer.Option(None, "--session", "-s", help="Continue an existing chat session."),
    agent: str = typer.Option(
        None, "--agent", "-a", help="Agent name or id. Default agent if omitted."
    ),
):
    """Start (or continue) a cloud agent chat and stream the turn live.

    Ctrl-C disconnects the stream, which stops the turn on the box."""
    with _client() as c:
        try:
            agent_id = _resolve_agent_id(c, agent) if agent else None
            session_id = _stream_turn(
                c.agent_chat_events(message, session_id=session, agent_id=agent_id)
            )
        except StashError as e:
            _err(e)
    if session_id:
        console.print(
            f"[dim]session {session_id} — continue with "
            f'[bold]stash agent chat -s {session_id} "…"[/bold][/dim]'
        )


@agent_app.command("run")
def agent_run(
    agent: str = typer.Argument(..., help="Scheduled agent name or id."),
):
    """Run a prompt-scheduled agent now and stream the run live."""
    with _client() as c:
        try:
            agent_id = _resolve_agent_id(c, agent)
            _stream_turn(c.agent_run_events(agent_id))
        except StashError as e:
            _err(e)


@agent_app.command("status")
def agent_status(
    session_id: str = typer.Argument(..., help="The chat session to check."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Whether a turn is currently running in a chat session."""
    with _client() as c:
        try:
            data = c.agent_turn_status(session_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    state = "[green]running[/green]" if data["running"] else "[dim]idle[/dim]"
    console.print(f"  {session_id}: {state}")


@agent_app.command("watch")
def agent_watch(
    session_id: str = typer.Argument(..., help="The chat session to follow."),
    poll_seconds: float = typer.Option(2.0, "--poll", help="Poll interval in seconds."),
):
    """Follow a chat session live — works for turns started anywhere
    (web, Slack, a schedule, or another terminal). Exits when the turn ends."""
    role_style = {"user": "[bold]you:[/bold] ", "assistant": "", "tool": "[dim]", "": ""}
    with _client() as c:
        seen = 0
        while True:
            try:
                # Status before messages: a turn that ends between the two
                # calls still gets its final message printed this pass.
                status = c.agent_turn_status(session_id)
                messages = c.get_agent_chat(session_id)["messages"]
            except StashError as e:
                _err(e)
            for m in messages[seen:]:
                prefix = role_style.get(m["role"], "")
                suffix = "[/dim]" if m["role"] == "tool" else ""
                console.print(f"{prefix}{m['content']}{suffix}\n")
            seen = len(messages)
            if not status["running"]:
                break
            time.sleep(poll_seconds)
    console.print("[dim]Turn finished — chat is idle.[/dim]")


@agent_app.command("stop")
def agent_stop(
    session_id: str = typer.Argument(..., help="The chat session whose turn to stop."),
):
    """Stop the turn running in a chat session (kills the run on the box)."""
    with _client() as c:
        try:
            c.stop_agent_turn(session_id)
        except StashError as e:
            _err(e)
    console.print("⏹ Stop requested — the turn will end shortly.")


# ===========================================================================
# Sources — unified VFS over native files/sessions + connected sources
# ===========================================================================

sources_app = typer.Typer(
    help="Sources — connect, sync, and disconnect external sources. "
    "Browse and read their contents with `stash vfs` under /sources."
)
app.add_typer(sources_app, name="sources")


def _print_search(query: str, source: str, limit: int, as_json: bool) -> None:
    """Shared body for `stash search`."""
    telemetry.record("sources.search")
    with _client() as c:
        try:
            data = c.search_sources(query, source=source or None, limit=limit)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    if not data:
        console.print("[dim]No matches.[/dim]")
        return
    for hit in data:
        label = hit.get("source_name") or hit.get("source")
        if hit.get("error"):
            console.print(f"  [yellow]⚠ {label}: {hit['error']}[/yellow]")
            continue
        if hit.get("truncated"):
            estimate = hit.get("estimated_total")
            of_total = f" of ~{estimate}" if estimate else ""
            console.print(
                f"  [dim]… {label}: showing first {hit.get('returned')}{of_total} matches — "
                f"narrow the query to see more.[/dim]"
            )
            continue
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
    limit: int = typer.Option(20, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Search everything you can see — files, sessions, and connected sources."""
    _print_search(query, source, limit, as_json)


def _poll_recompute_outcome(
    c: StashClient, before: dict | None, attempts: int = 15
) -> tuple[str, str | None]:
    """Watch the enqueued curator run get picked up by the worker.

    The recompute API answers 202 before anything executes — the web service
    can't see the worker's world, so "started" is only real once last_run_at
    advances on the agent row. mark_run clears last_run_error at pickup, so an
    error present after that means THIS run died (crashes happen within
    seconds; the multi-minute happy path reports "running")."""
    baseline = (before or {}).get("last_run_at")
    for _ in range(attempts):
        time.sleep(2)
        curator = c.get_curator()
        if not curator or curator["last_run_at"] == baseline:
            continue
        if curator["last_run_error"]:
            return "failed", curator["last_run_error"]
        return "running", None
    return "queued", None


@app.command("memory")
def memory(
    recompute: bool = typer.Option(
        False,
        "--recompute",
        help="Run the Memory curator now instead of waiting for the daily pass.",
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show your reserved Memory folder (its id is where the wiki lives)."""
    with _client() as c:
        if recompute:
            before = c.get_curator()
            data = c.recompute_memory()
            outcome, run_error = _poll_recompute_outcome(c, before)
            if _use_json(as_json):
                output_json({**data, "outcome": outcome, "last_run_error": run_error})
            elif outcome == "failed":
                console.print(f"[red]Curator run failed:[/red] {run_error}")
            elif outcome == "queued":
                console.print(
                    "[yellow]Curator run was enqueued but no worker picked it up "
                    "within 30s — it may still run; check `stash memory` later.[/yellow]"
                )
            else:
                console.print(
                    "Curator run started — the Memory wiki will update shortly. "
                    "Check `stash memory` for the outcome."
                )
            if outcome == "failed":
                raise typer.Exit(1)
            return
        folder = c.get_memory_folder()
        curator = c.get_curator()
    if _use_json(as_json):
        output_json({**folder, "curator": curator})
        return
    console.print(f"Memory folder: [cyan]{folder['name']}[/cyan] (id {folder['id']})")
    if curator:
        last_run = curator["last_run_at"] or "never"
        console.print(f"Curator last run: {last_run}")
        if curator["last_run_error"]:
            console.print(f"[red]Curator last run failed:[/red] {curator['last_run_error']}")


@app.command("changes")
def changes(
    since: str = typer.Option(None, "--since", help="ISO timestamp; omit for everything."),
    as_json: bool = typer.Option(False, "--json"),
):
    """What changed since a timestamp — history, pages, files, sources. Feeds
    the Memory curator's incremental pass."""
    with _client() as c:
        data = c.get_changes(since or None)
    if _use_json(as_json):
        output_json(data)
        return
    counts = data.get("counts", {})
    console.print(
        f"Changes since {data.get('since') or 'the beginning'}: "
        f"{counts.get('sessions', 0)} sessions, {counts.get('pages', 0)} pages, "
        f"{counts.get('files', 0)} files, {counts.get('sources', 0)} sources"
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Connect a source. Slack/Granola resolve their ref from your token."""
    with _client() as c:
        try:
            data = c.add_source(source_type, external_ref=ref or None, display_name=name or None)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(f"[green]Connected[/green] {data['display_name']}  [dim]→ {data['id']}[/dim]")


@sources_app.command("sync")
def sources_sync(
    source_id: str = typer.Argument(...),
    as_json: bool = typer.Option(False, "--json"),
):
    """Trigger an immediate re-index of a connected source you own."""
    with _client() as c:
        try:
            data = c.sync_source(source_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(f"[green]Sync queued[/green]  [dim]task: {data.get('task_id')}[/dim]")


@sources_app.command("rm")
def sources_rm(source_id: str = typer.Argument(...)):
    """Disconnect a source you own (its indexed documents cascade away)."""
    with _client() as c:
        try:
            c.delete_source(source_id)
        except StashError as e:
            _err(e)
    console.print("[green]Source removed.[/green]")


def _safe_slug(name: str) -> str:
    import re as _re

    return _re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-") or "source"


def _source_dir_names(sources: list[dict]) -> dict[str, dict]:
    """Stable filesystem-style directory name per source. Natives keep their
    handle ('files', 'sessions'); connected sources slug their display name,
    with -2/-3 suffixes on collisions."""
    names: dict[str, dict] = {}
    for s in sources:
        if s["type"].startswith("native_"):
            name = s["source"]
        else:
            name = _safe_slug(s["display_name"])
        candidate = name
        suffix = 2
        while candidate in names:
            candidate = f"{name}-{suffix}"
            suffix += 1
        names[candidate] = s
    return names


def _source_annotation(s: dict) -> str:
    note = "" if s["type"] == "provider" else f"  [dim]({s['type']})[/dim]"
    if s.get("sync_status") == "failed":
        note += "  [red]sync failed[/red]"
    elif s.get("sync_status") == "syncing":
        note += "  [yellow]syncing…[/yellow]"
    return note


def _add_ls_branch(branch, nodes: list[dict]) -> None:
    for node in nodes:
        if node["kind"] == "truncated":
            branch.add(f"[dim]… +{node['hidden']} more[/dim]")
        elif node.get("children") or node["kind"] == "folder":
            child = branch.add(f"[bold]{node['name']}/[/bold]")
            _add_ls_branch(child, node.get("children") or [])
        else:
            branch.add(node["name"])


@app.command("ls")
def ls_cmd(
    path: str = typer.Argument(
        "", help="Source or path to list, e.g. 'gong' or 'my-repo/docs'. Omit for everything."
    ),
    depth: int = typer.Option(2, "-L", "--depth", help="How many levels deep to render."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Everything Stash can reach, as one filesystem — files, session
    transcripts, and every connected integration (GitHub, Slack, Gong, …)."""
    telemetry.record("ls")
    _require_auth()

    with _client() as c:
        try:
            sources = c.sources_tree(depth=depth)
            if not path:
                _print_ls_overview(sources, as_json)
                return
            _print_ls_path(c, sources, path, as_json)
        except StashError as e:
            _err(e)


def _print_ls_overview(sources: list[dict], as_json: bool) -> None:
    if _use_json(as_json):
        output_json({"sources": sources})
        return
    from rich.tree import Tree as RichTree

    root = RichTree("[bold]stash:/[/bold]")
    for name, s in _source_dir_names(sources).items():
        branch = root.add(f"[bold]{name}/[/bold]{_source_annotation(s)}")
        _add_ls_branch(branch, s.get("tree") or [])
    console.print(root)


def _print_ls_path(c: StashClient, sources: list[dict], path: str, as_json: bool) -> None:
    dir_name, _, rest = path.strip("/").partition("/")
    source = _source_dir_names(sources).get(dir_name)
    if source is None:
        console.print(f"[red]No source named '{dir_name}'. Run `stash ls` to see them.[/red]")
        raise typer.Exit(1)

    if source["type"] == "provider":
        _print_provider_path(c, source, rest, as_json)
        return

    entries = c.list_source_entries(source["source"], path=rest)
    if _use_json(as_json):
        output_json({"entries": entries})
        return
    for entry in entries:
        console.print(f"  {entry['name']}  [dim]({entry.get('id', '')})[/dim]")


def _print_provider_path(c: StashClient, provider: dict, rest: str, as_json: bool) -> None:
    """Drill into a provider folder. A sole connection collapses, so `rest` is a
    document path read straight against it; otherwise the first segment selects
    the connection (repo, account) and the remainder is the document path."""
    members = provider.get("members") or []
    if len(members) == 1:
        handle, doc_path = members[0]["handle"], rest
    else:
        member_slug, _, doc_path = rest.partition("/")
        if not member_slug:
            _print_connection_dirs(members, as_json)
            return
        member = next((m for m in members if _safe_slug(m["display_name"]) == member_slug), None)
        if member is None:
            console.print(f"[red]No connection '{member_slug}' under '{provider['source']}'.[/red]")
            raise typer.Exit(1)
        handle = member["handle"]

    entries = c.list_source_entries(handle, path=doc_path)
    if _use_json(as_json):
        output_json({"entries": entries})
        return
    _print_dir_children(entries, doc_path)


def _print_connection_dirs(members: list[dict], as_json: bool) -> None:
    if _use_json(as_json):
        output_json({"entries": [{"name": m["display_name"], "kind": "folder"} for m in members]})
        return
    for member in members:
        console.print(f"  [bold]{_safe_slug(member['display_name'])}/[/bold]")


def _print_dir_children(entries: list[dict], base_path: str) -> None:
    """Entries are a recursive prefix listing; collapse to this directory's
    immediate children."""
    base = f"{base_path}/" if base_path else ""
    children: dict[str, str] = {}
    for entry in entries:
        entry_path = entry.get("path") or ""
        if entry_path == base_path:
            children[entry_path.rsplit("/", 1)[-1]] = entry.get("kind", "file")
            continue
        if not entry_path.startswith(base):
            continue
        name, _, remainder = entry_path[len(base) :].partition("/")
        if remainder or entry.get("kind") == "folder":
            children[name] = "folder"
        else:
            children.setdefault(name, entry.get("kind", "file"))
    if not children:
        console.print("[dim]Empty.[/dim]")
        return
    for name in sorted(children):
        console.print(f"  [bold]{name}/[/bold]" if children[name] == "folder" else f"  {name}")


# ===========================================================================
# Object operations — rm / restore / mv / cp across every object type
# ===========================================================================

_OBJECT_TYPES = "page | file | folder | session | table"


def _parse_refs(refs: list[str]) -> list[tuple[str, str]]:
    """Parse `type:id` tokens (e.g. page:abc session:def) into (type, id) pairs."""
    parsed = []
    for ref in refs:
        if ":" not in ref:
            console.print(f"[red]Invalid item '{ref}' — use type:id, e.g. page:<id>[/red]")
            raise typer.Exit(1)
        object_type, object_id = ref.split(":", 1)
        parsed.append((object_type, object_id))
    return parsed


@app.command("rm")
def rm_cmd(
    refs: list[str] = typer.Argument(..., help="Items as type:id. Types: page | file | session"),
    permanent: bool = typer.Option(
        False, "--permanent", help="Skip the trash window — delete immediately."
    ),
):
    """Move pages, files, or sessions to trash. Pass --permanent to wipe immediately.

    Example: stash rm page:<id> file:<id> session:<id>
    """
    trash = {
        "page": (lambda c, i: c.delete_page(i), lambda c, i: c.purge_page(i)),
        "file": (lambda c, i: c.delete_file(i), lambda c, i: c.purge_file(i)),
        "session": (lambda c, i: c.delete_session(i), lambda c, i: c.purge_session(i)),
    }
    items = _parse_refs(refs)
    with _client() as c:
        for object_type, object_id in items:
            if object_type not in trash:
                console.print(
                    f"[red]Cannot rm '{object_type}'. Supported: page | file | session[/red]"
                )
                raise typer.Exit(1)
            delete, purge = trash[object_type]
            try:
                delete(c, object_id)
                if permanent:
                    purge(c, object_id)
            except StashError as e:
                _err(e)
    verb = "permanently deleted" if permanent else "moved to trash"
    console.print(f"[green]{len(items)} item(s) {verb}.[/green]")


@app.command("restore")
def restore_cmd(
    refs: list[str] = typer.Argument(..., help="Items as type:id. Types: page | file | session"),
):
    """Restore pages, files, or sessions from trash.

    Example: stash restore page:<id> session:<id>
    """
    restore = {
        "page": lambda c, i: c.restore_page(i),
        "file": lambda c, i: c.restore_file(i),
        "session": lambda c, i: c.restore_session(i),
    }
    items = _parse_refs(refs)
    with _client() as c:
        for object_type, object_id in items:
            if object_type not in restore:
                console.print(
                    f"[red]Cannot restore '{object_type}'. Supported: page | file | session[/red]"
                )
                raise typer.Exit(1)
            try:
                restore[object_type](c, object_id)
            except StashError as e:
                _err(e)
    console.print(f"[green]{len(items)} item(s) restored.[/green]")


@app.command("mv")
def mv_cmd(
    refs: list[str] = typer.Argument(..., help=f"Items as type:id. Types: {_OBJECT_TYPES}"),
    to_folder: str = typer.Option(None, "--to-folder", help="Target folder id."),
    to_root: bool = typer.Option(False, "--to-root", help="Move to the root."),
):
    """Move objects into a folder (or to the root with --to-root).

    Example: stash mv page:<id> file:<id> --to-folder <id>
    """
    if not to_folder and not to_root:
        console.print("[red]Pass --to-folder <id> or --to-root.[/red]")
        raise typer.Exit(1)
    items = _parse_refs(refs)
    sessions = [i for t, i in items if t == "session"]
    others = [{"object_type": t, "object_id": i} for t, i in items if t != "session"]
    with _client() as c:
        try:
            if others:
                c.batch_move(others, target_folder_id=to_folder, move_to_root=to_root)
            for session_id in sessions:
                c.assign_session_folder(session_id, folder_id=None if to_root else to_folder)
        except StashError as e:
            _err(e)
    console.print(f"[green]{len(items)} item(s) moved.[/green]")


@app.command("cp")
def cp_cmd(
    refs: list[str] = typer.Argument(..., help="Items as type:id. Types: page | file | folder"),
    to_folder: str = typer.Option(None, "--to-folder", help="Target folder id."),
):
    """Duplicate pages, files, or folders as 'Copy of <name>'.

    Example: stash cp page:<id> folder:<id> --to-folder <id>
    """
    copy = {
        "page": lambda c, i: c.copy_page(i, target_folder_id=to_folder or None),
        "file": lambda c, i: c.copy_file(i, target_folder_id=to_folder or None),
        "folder": lambda c, i: c.copy_folder(i, target_folder_id=to_folder or None),
    }
    for object_type, object_id in _parse_refs(refs):
        if object_type not in copy:
            console.print(f"[red]Cannot cp '{object_type}'. Supported: page | file | folder[/red]")
            raise typer.Exit(1)
        with _client() as c:
            try:
                made = copy[object_type](c, object_id)
            except StashError as e:
                _err(e)
        console.print(f"[green]Copied to[/green] {made['name']} ({made['id']})")


# ===========================================================================
# Shares — grant a person access to a folder/page/file/session by email
# ===========================================================================

shares_app = typer.Typer(help="Shares — grant people access to an object by email.")
app.add_typer(shares_app, name="shares")

_SHARE_OBJECT_TYPES = "folder | page | file | session | session_folder | table | source"


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
        except StashError as e:
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
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
        return
    console.print(
        f"[green]Shared[/green] with {email} ({permission}). "
        "If they don't have an account yet, it converts when they sign up."
    )


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
        except StashError as e:
            _err(e)
    console.print("[green]Access revoked.[/green]")


# ===========================================================================
# Trash
# ===========================================================================

trash_app = typer.Typer(help="Trash — soft-deleted pages, files, and sessions.")
app.add_typer(trash_app, name="trash")


@trash_app.command("list")
def trash_list(as_json: bool = typer.Option(False, "--json")):
    """List trashed pages, files, and sessions."""
    with _client() as c:
        try:
            data = c.get_trash()
        except StashError as e:
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


@tables_app.command("create")
def tables_create(
    name: str = typer.Argument(...),
    description: str = typer.Option(""),
    columns: str = typer.Option(None, "--columns", help='JSON: [{"name":"Col","type":"text"}]'),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a table. --columns accepts JSON array of {name, type, options?}."""
    cols = json.loads(columns) if columns else []
    with _client() as c:
        try:
            data = c.create_table(name, description=description, columns=cols)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]Table '{data['name']}' created.[/green]  ID: {data['id']}")


@tables_app.command("update")
def tables_update(
    table_id: str = typer.Argument(...),
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
            data = c.update_table(table_id, **kwargs)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print("[green]Table updated.[/green]")


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


def _apply_uploads(c: StashClient, row_data: dict, uploads: dict[str, str]) -> dict:
    """Upload each file and set the file URL as the value for the named column.
    Explicit values already in row_data for the same column take precedence."""
    for col, path in uploads.items():
        if col in row_data:
            continue
        f = c.upload_file(path)
        row_data[col] = f["url"]
    return row_data


@tables_app.command("insert")
def tables_insert(
    table_id: str = typer.Argument(...),
    data: str = typer.Argument(..., help='JSON: {"Name":"Alice","Status":"active"}'),
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
            row_data = _apply_uploads(c, row_data, uploads)
            table = c.get_table(table_id)
            resolved = _resolve_col_names(table, row_data)
            result = c.insert_table_row(table_id, resolved)
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
            table = c.get_table(table_id)

            # Resolve column names to IDs
            resolved_rows = [_resolve_col_names(table, r) for r in rows_data]

            # Chunk into batches of 5000
            batch_size = 5000
            total_inserted = 0
            for i in range(0, len(resolved_rows), batch_size):
                batch = resolved_rows[i : i + batch_size]
                c.insert_table_rows_batch(table_id, batch)
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
            row_data = _apply_uploads(c, row_data, uploads)
            table = c.get_table(table_id)
            resolved = _resolve_col_names(table, row_data)
            result = c.update_table_row(table_id, row_id, resolved)
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
):
    """Delete a row from a table."""
    with _client() as c:
        try:
            c.delete_table_row(table_id, row_id)
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Add a column to a table."""
    opts = [o.strip() for o in options.split(",") if o.strip()] if options else None
    with _client() as c:
        try:
            result = c.add_table_column(table_id, name, col_type=col_type, options=opts)
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Delete a column from a table."""
    with _client() as c:
        try:
            # Resolve column name to ID if needed
            if not column_id.startswith("col_"):
                table = c.get_table(table_id)
                name_to_id = {col["name"]: col["id"] for col in table.get("columns", [])}
                if column_id in name_to_id:
                    column_id = name_to_id[column_id]
            result = c.delete_table_column(table_id, column_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print("[green]Column deleted.[/green]")


@tables_app.command("count")
def tables_count(
    table_id: str = typer.Argument(...),
    filters: str = typer.Option("", "--filter", help="JSON filter array"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Count rows, optionally with filters."""
    with _client() as c:
        try:
            if filters:
                table = c.get_table(table_id)
                filters = _resolve_filter_names(table, filters)
            params: dict = {}
            if filters:
                params["filters"] = filters
            result = c._get(f"/api/v1/me/tables/{table_id}/rows/count", **params)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
    else:
        console.print(f"Count: {result.get('count', 0)}")


@tables_app.command("export")
def tables_export(
    table_id: str = typer.Argument(...),
    file: str = typer.Option(None, "--file", "-f", help="Output file (default: stdout)"),
    filters: str = typer.Option("", "--filter"),
    sort_by: str = typer.Option("", "--sort"),
    sort_order: str = typer.Option("asc", "--order"),
):
    """Export table as CSV."""
    with _client() as c:
        try:
            params: dict = {"sort_order": sort_order}
            if sort_by:
                table = c.get_table(table_id)
                params["sort_by"] = _resolve_sort_name(table, sort_by)
            if filters:
                if "table" not in dir():
                    table = c.get_table(table_id)
                params["filters"] = _resolve_filter_names(table, filters)
            resp = c._request("GET", f"/api/v1/me/tables/{table_id}/export/csv", params=params)
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
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """Delete a table and all its data."""
    if not yes:
        typer.confirm("Delete this table and all its data?", abort=True)
    with _client() as c:
        try:
            c.delete_table(table_id)
        except StashError as e:
            _err(e)
    console.print("[green]Table deleted.[/green]")


# ===========================================================================
# Uploaded files
# ===========================================================================


def _upload_path(c: StashClient, path: str) -> dict:
    """Upload `path` to your Files. Returns FileResponse dict."""
    if not Path(path).is_file():
        console.print(f"[red]Not a file: {path}[/red]")
        raise typer.Exit(1)
    return c.upload_file(path)


def _get_file_meta(c: StashClient, file_id: str) -> dict:
    return c.get_file(file_id)


@files_app.command("edit-file")
def files_edit_file(
    file_id: str = typer.Argument(...),
    name: str = typer.Option(..., "--name", help="New file name."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Rename a file. Use `stash mv` to relocate it."""
    with _client() as c:
        try:
            data = c.update_file(file_id, name=name)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(data)
    else:
        console.print(f"[green]File renamed.[/green] {data['name']}  [dim]{data['id']}[/dim]")


@files_app.command("text")
def files_text(file_id: str = typer.Argument(...)):
    """Print extracted text for a file (PDFs with embedded text, or plain text)."""
    with _client() as c:
        try:
            data = c.get_file_text(file_id)
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


def _parse_file_ref(ref: str) -> str:
    """A file id, or the embed link a page carries (/api/v1/me/files/<id>/download)."""
    match = re.fullmatch(r".*/files/([^/]+)/download", ref)
    return match.group(1) if match else ref


@files_app.command("download")
def files_download(
    file_ref: str = typer.Argument(
        ..., help="File id, or the embed link from a page (/api/v1/me/files/<id>/download)."
    ),
    output: str = typer.Option(
        None, "--output", "-o", help="Destination path. Defaults to the file's name in cwd."
    ),
):
    """Download a file's bytes to a local path.

    Files a page embeds don't appear in the files tree — the page's
    markdown links them. Read the page, then download a linked file
    only when you need its contents."""
    file_id = _parse_file_ref(file_ref)
    with _client() as c:
        try:
            meta = c.get_file(file_id)
            data = c.download_file(file_id)
        except StashError as e:
            _err(e)
    dest = Path(output) if output else Path(meta["name"])
    dest.write_bytes(data)
    console.print(f"[green]Downloaded[/green] {meta['name']} → {dest} [dim]{len(data)} bytes[/dim]")


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
        console.print("[red]Not authenticated. Run `stash signin` first.[/red]")
        raise typer.Exit(1)
    return cfg


def _auto_connect_repo(repo_root: Path, cfg: dict) -> None:
    """Connect a repo to Stash: write `.stash`, enable streaming, append CLAUDE.md."""
    manifest_path = repo_root / MANIFEST_FILE

    if manifest_path.is_file():
        console.print("  [green]✓[/green] Already connected.")
        return

    base_url = cfg.get("base_url", PRODUCTION_BASE_URL)

    manifest: Manifest = {}
    if base_url != PRODUCTION_BASE_URL:
        manifest["base_url"] = base_url

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    console.print(f"  Wrote [cyan]{MANIFEST_FILE}[/cyan]")

    start_streaming()

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

### What a Skill is

A Skill is a *special folder* — one containing a SKILL.md — holding related artifacts
(pages, files, tables) that shares like any folder and gains a public URL when
published. Use one when you're publishing a *collection* of related things together — a
project writeup with its supporting files, a research thread with its sources, a session
transcript frozen as a page plus the files it produced.

A Skill is **not** a wrapper to slap on every single file you happen to share. One-item Skills
clutter Discover and defeat the model. Pick the right tool:

- Share a single file or a folder/project → `stash upload <path> --json`, hand over `app_url` (no Skill).
- Publishing a curated bundle → `stash upload <path> --skill "<title>" --json`.
- Creating a fresh skill → `stash skills create "<name>" --public --json`.
- Share a coding session → `stash share <session_id>`.

Run `stash prompts agent-guidance` to reprint this rule mid-session.

### Browsing Stash

Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS:
- `stash vfs ls /`
- `stash vfs "find / -maxdepth 3 -type f"`
- `stash vfs "rg 'query' /"`
- `stash vfs "cat '/files/README.md' | sed -n '1,80p'"`

Common reads:
- `stash search "<query>" --json` — full-text search across files, sessions, and connected sources
- `stash vfs "ls /"` — browse your files, sessions, tables, skills, and connected sources
- `stash vfs "cat '/sessions/_index.jsonl'"` — recent sessions
- `stash sessions agents` — who's been active

Common writes:
- `stash share --title "..."` — share this session as a public Skill
- `stash read <url>` — read a public Skill URL
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


@app.command()
def signin(
    api: str = typer.Option(
        None, "--api", help="Stash API base URL. Override for self-hosted deployments."
    ),
    api_key: str = typer.Option(
        None,
        "--api-key",
        help="Store this pre-minted key directly instead of signing in through a "
        "browser. For unattended, browser-less machines (typically self-hosted CI). "
        "Get the key from your self-hosted instance's API-key page.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Skip the setup wizard; just authenticate. For installers and agents. "
        "Implied when stdin isn't a terminal.",
    ),
    timeout: int = typer.Option(120, "--timeout", help="Seconds to wait for sign-in."),
):
    """Sign in to Stash through the browser.

    Run interactively for guided first-run setup (endpoint, streaming agents,
    repo). With --non-interactive — or whenever stdin isn't a terminal — it
    skips the wizard and just authenticates, which is the path installers and
    agents use. The browser opens automatically when one is available, and
    otherwise a URL is printed to visit. For a fully unattended, browser-less
    machine, pass --api-key to store a pre-minted key directly (no handshake).
    """
    # Direct key injection — no browser handshake. The streaming hooks read
    # ~/.stash/config.json, not env vars, so this is how a browser-less box
    # (typically a self-hosted CI runner) gets a key into that file. The key
    # defines which self-hosted server it belongs to, so --api is required:
    # such a box has never run an interactive sign-in, so nothing else could
    # have established the endpoint.
    if api_key:
        if not api:
            console.print(
                "[red]Pass --api <url> with --api-key — the server that minted the key.[/red]"
            )
            raise typer.Exit(1)
        try:
            with StashClient(base_url=api, api_key=api_key) as c:
                user = c.whoami()
        except StashError as e:
            console.print(f"[red]Could not authenticate against {api}: {e.detail}[/red]")
            raise typer.Exit(1)
        save_config(base_url=api, api_key=api_key, username=user["name"])
        console.print(f"[green]Authenticated as {user['name']}[/green]")
        return

    # Scripted / headless: bare browser auth, no wizard prompts.
    if non_interactive or not sys.stdin.isatty():
        base_url = api or stored_base_url() or PRODUCTION_BASE_URL
        api_key, username = _browser_auth_flow(base_url, timeout=timeout)
        save_config(base_url=base_url, api_key=api_key, username=username)
        console.print(f"[green]✓ Signed in as {username}[/green]")
        return

    console.print("\n[bold]Stash sign-in[/bold]\n")

    cfg = load_config()

    # --- Step 1: API endpoint ---
    prev_base = api or stored_base_url()
    if prev_base:
        base_url = prev_base
        save_config(base_url=base_url)
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
        _install_all_hooks(load_enabled_agents())
        console.print("\n  Run [cyan]stash settings[/cyan] to change agents or endpoint.")
        return

    # --- Step 3: Share transcripts? ---
    _reserve_bottom_padding(4)
    share_transcripts = questionary.confirm(
        "Do you want to share your coding agent transcripts to Stash?",
        default=True,
    ).ask()
    if share_transcripts is None:
        raise typer.Exit(1)

    if not share_transcripts:
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
    # Outside a git repo, treat the current directory as the repo root: the
    # .stash manifest lands there.
    repo_root = _git_toplevel() or Path.cwd()

    repo_choices = [
        questionary.Choice(f"This repo ({repo_root.name})", value="this"),
        questionary.Choice("Another repo", value="other"),
        questionary.Choice("Done", value="done"),
    ]
    _reserve_bottom_padding(6)
    answer = questionary.select(
        "Which repo do you want to upload transcripts in?",
        choices=repo_choices,
        default=repo_choices[0],
        use_shortcuts=True,
    ).ask()
    if answer is None:
        raise typer.Exit(1)

    if answer == "this":
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

    # --- Step 6: Import historical conversations ---
    _onboarding_import_history(detected)

    _show_setup_complete_splash()


@app.command("connect")
def connect_cmd():
    """Connect this repo to Stash so its agent sessions stream to your scope."""
    cfg = _require_auth()
    telemetry.record("connect")

    repo_root = _git_toplevel()
    if not repo_root:
        console.print("[red]Not inside a git repo.[/red]")
        raise typer.Exit(1)

    _auto_connect_repo(repo_root, cfg)


@app.command("start")
def start_cmd():
    """Resume streaming transcripts globally (undoes `stash stop`)."""
    _require_auth()
    start_streaming()
    console.print("  [green]✓[/green] Streaming enabled.")


@app.command("stop")
def stop_cmd():
    """Stop streaming transcripts globally."""
    _require_auth()
    stop_streaming()
    console.print("  [green]✓[/green] Streaming stopped.")


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


def _home_url() -> str:
    """The user-facing link to the signed-in user's home on the configured frontend."""
    return _frontend_base_url()


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

    if _enable_marketplace_autoupdate(Path.home() / ".claude" / "settings.json"):
        console.print("  [green]✓[/green] auto-update enabled for the stash-plugins marketplace")
    else:
        console.print(
            "  [yellow]Could not update ~/.claude/settings.json — enable auto-update "
            "manually: /plugin → Marketplaces → stash-plugins → Enable auto-update. "
            "Without it the plugin never updates itself.[/yellow]"
        )

    # Freshen right now regardless: until this run set autoUpdate (or on Claude
    # Code versions that ignore the key at user scope), the marketplace clone
    # and plugin may be weeks stale. Best-effort — a failure here still leaves
    # a working install, and the plugin's session-start drift warning names any
    # remaining staleness.
    for cmd in (
        ["claude", "plugin", "marketplace", "update", "stash-plugins"],
        ["claude", "plugin", "update", "stash@stash-plugins"],
    ):
        try:
            _sp.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except (_sp.CalledProcessError, FileNotFoundError, _sp.TimeoutExpired) as e:
            console.print(f"  [yellow]`{' '.join(cmd)}` failed: {e}[/yellow]")
            break
    else:
        console.print("  [green]✓[/green] marketplace and plugin updated to latest")
    return True


def _enable_marketplace_autoupdate(settings_path: Path) -> bool:
    """Set `autoUpdate: true` on the stash-plugins marketplace in Claude Code's
    user settings.

    Claude Code auto-updates plugins from the official marketplace only;
    third-party marketplaces like ours default to auto-update OFF, which
    fossilizes the installed plugin (a machine ran June's hook scripts for a
    month this way). `extraKnownMarketplaces.<name>.autoUpdate` is the settings
    key documented for enabling it without the /plugin menu.

    Returns False without writing when the settings file is unparseable —
    clobbering a user's hand-edited settings.json is worse than a manual toggle.
    """
    try:
        data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    marketplaces = data.setdefault("extraKnownMarketplaces", {})
    entry = marketplaces.setdefault(
        "stash-plugins", {"source": {"source": "github", "repo": "Fergana-Labs/stash"}}
    )
    if entry.get("autoUpdate") is True:
        return True
    entry["autoUpdate"] = True
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
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

    from rich.progress import Progress

    imported = 0
    errors = 0
    last_error = ""
    with _client() as c, Progress(console=console) as progress:
        task = progress.add_task("Importing…", total=len(conversations))
        for conv in conversations:
            try:
                upload_conversation(c, conv)
                imported += 1
            except (StashError, httpx.HTTPError) as e:
                errors += 1
                last_error = str(e)
            progress.advance(task)

    console.print(f"  [green]��[/green] Imported {imported} conversations")
    if errors:
        console.print(f"  [yellow]{errors} failed — {last_error}[/yellow]")


def _setup_complete_intro(home_url: str, connected: bool) -> str:
    home_link_section = (
        "[bold]See your Stash[/bold]   [dim](transcripts and activity)[/dim]\n"
        f"  [link={home_url}][bold #1e3a8a]{home_url}[/bold #1e3a8a][/link]\n"
        "\n"
        if connected
        else ""
    )
    memory_section = (
        "It can read the transcripts your coding agents push to Stash — so it\n"
        "knows what you've been working on.\n"
        "\n"
        if connected
        else "No repo is connected yet. Run [cyan]stash connect[/cyan] from a git repo when\n"
        "you're ready to upload transcripts.\n"
        "\n"
    )
    next_section = (
        "[bold]You're streaming[/bold]\n"
        "This repo's agent sessions now upload to your Stash automatically."
        if connected
        else "[bold]Connect a repo when ready[/bold]\n"
        "Run [cyan]stash connect[/cyan] from the repo you want Stash to remember."
    )
    return (
        "[bold]What just happened[/bold]\n"
        "Your coding agent now has the [bold #1e3a8a]stash[/bold #1e3a8a] CLI on its PATH.\n"
        f"{memory_section}"
        f"{home_link_section}"
        "[bold]Commands your agent can now use[/bold]\n"
        '  [#1e3a8a]stash vfs "find / -maxdepth 3 -type f"[/#1e3a8a]   browse Stash like a filesystem\n'
        '  [#1e3a8a]stash search "<query>"[/#1e3a8a]   full-text search across files, sessions, and sources\n'
        "  [#1e3a8a]stash sessions agents[/#1e3a8a]   see which agents have been active\n"
        "\n"
        "Run [bold]stash --help[/bold] to see everything.\n"
        "\n"
        f"{next_section}"
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

    connected = load_manifest() is not None
    console.print(
        Panel(
            Text.from_markup(_setup_complete_intro(_home_url(), connected)),
            title="[bold #1e3a8a]Your agent memory[/bold #1e3a8a]",
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
    # Claude Code names the data dir <plugin>-<marketplace>.
    "claude": Path.home() / ".claude/plugins/data/stash-stash-plugins",
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

    repo_label = "connected" if load_manifest() is not None else "(none — no .stash file)"

    def row(label: str, value: str, *, highlight: bool = True) -> None:
        console.print(f"  [dim]{label}[/dim]{value}", highlight=highlight)

    row(f"{'User:':<14}", cfg.get("username") or "(not logged in)")
    row(f"{'Repo:':<14}", repo_label, highlight=False)

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
                "session_link": session_link_enabled(),
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
            ("Session link", "on" if session_link_enabled() else "off", "session_link"),
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
        elif picked == "session_link":
            answer = questionary.confirm(
                "Append the session record link to every Claude response?",
                default=session_link_enabled(),
            ).ask()
            if answer is not None:
                set_session_link(answer)
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
    """Sign out and clear credentials. Hooks go inert until you `stash signin` again."""
    from .config import clear_config

    json_mode = as_json
    clear_config()
    if json_mode:
        output_json({"logged_out": True})
        return
    console.print("[yellow]Logged out.[/yellow] Cleared auth and preferences.")
    console.print("  Run [bold]stash signin[/bold] to sign in again.")


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

    # Streaming is global to the user's scope, so disconnecting one repo leaves it
    # untouched — run `stash stop` to halt streaming everywhere.
    manifest_path.unlink()
    console.print(f"  [green]✓[/green] Removed [cyan]{MANIFEST_FILE}[/cyan] — repo disconnected.")


@app.command("vfs", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def vfs_command(
    ctx: typer.Context,
    cwd: str = typer.Option("/", "--cwd", help="Virtual working directory."),
):
    """Run bash-shaped commands against Stash sources."""
    from stashvfs import MountError, SkillAppVfsShell, StashVfsModel

    cfg = load_config()
    if not cfg.get("api_key"):
        console.print("[red]Not signed in. Run [bold]stash signin[/bold] first.[/red]")
        raise typer.Exit(1)

    client = StashClient(base_url=cfg["base_url"], api_key=cfg["api_key"])
    try:
        model = StashVfsModel(client, include_computer=True)
        model.refresh()
        shell = SkillAppVfsShell(model, cwd=cwd)

        command = " ".join(ctx.args).strip()
        if not command:
            console.print(
                '[red]Usage: stash vfs "<command>" (e.g. [bold]stash vfs "ls /me"[/bold]).[/red]'
            )
            raise typer.Exit(2)

        result = shell.run(command)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.exit_code:
            raise typer.Exit(result.exit_code)
    except MountError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    finally:
        client.close()


# ===========================================================================
# Prompts — reusable agent-facing prompts the CLI can hand back as text
# ===========================================================================

prompts_app = typer.Typer(help="Print reusable stash agent prompts.")
app.add_typer(prompts_app, name="prompts")


# Canonical explanation of what a Skill is and when to create one. Shared
# verbatim by the SessionStart hooks, the plugin CLAUDE.md, and this command,
# so every agent surface tells the same story.
AGENT_GUIDANCE_PROMPT = """\
What a Skill is
===============

A Skill is a special folder — one containing a SKILL.md — holding related
artifacts (pages, files, tables) that shares like any folder and gains a
public URL when published. Use one when you're publishing a collection of
related things together — a project writeup with its supporting files, a
research thread with its sources, a session transcript frozen as a page
with its outputs.

When to create a Skill
----------------------

Create a Skill when:
- You're publishing a curated collection of related artifacts that belong
  together as one share.
- You want a single public URL for the whole collection (publish it), or
  to hand a teammate everything at once (share the folder).

Do NOT create a Skill when:
- The user just wants the link to one file or page. Give them its
  `app_url`.
- You're emitting incidental artifacts (logs, intermediate outputs).
  Upload them with `stash upload` and pass the `app_url` back.

Commands to reach for
---------------------

- `stash upload <path> --json` — a single file (Markdown/HTML become pages,
  everything else a binary file) or a folder, into your storage. Returns
  `app_url`. No Skill created. This is the default for "share this one
  file."
- `stash upload <path> --skill "<title>" --json` — same as above AND
  publish the uploaded folder as a Skill with the given title. Use only
  when you're producing a shareable collection.
- `stash skills create "<name>" --public --json` — create a fresh skill
  folder (with a SKILL.md template) and publish it. Add content with the
  normal files/pages commands; `stash skills publish <folder_id>` shares
  an existing skill folder.
- `stash share <session_id>` — freeze a coding session (transcript + the
  files it touched) into a Skill folder. Sessions are inherently a
  collection, so this is the right unit.
- `stash skills install <slug>` — install a public Skill (e.g. from
  Discover) into ~/.claude/skills so the local agent loads it next
  session. `--project` targets ./.claude/skills instead.
- `stash skills sync` — two-way sync between the local skills directory
  and your skills: your skills materialize locally, local edits to synced
  skills push back. Runs automatically at session start, targeting each
  agent's own skills dir (Claude `~/.claude/skills`, Codex/Gemini/OpenCode
  `~/.agents/skills`, OpenClaw `~/.openclaw/skills`).

Browsing Stash
--------------

`stash ls` shows everything Stash can reach as one filesystem — your files,
session transcripts, and every connected integration (GitHub, Slack, Gong,
Gmail, Drive, Notion, …). When asked what you have access to, run it and
show the tree. Drill in with `stash ls <source>/<path>`, and read a
document with `stash vfs "cat '/sources/<source>/<path>'"`.

Use `stash vfs` when you want to browse Stash like a filesystem without
mounting anything into the OS. It accepts bash-shaped commands over the
virtual Stash tree:

- `stash vfs ls /`
- `stash vfs "find / -maxdepth 3 -type f"`
- `stash vfs "rg 'query' /"`
- `stash vfs "cat '/files/README.md' | sed -n '1,80p'"`

Anti-pattern: minting one Stash per file you happen to share. Skills
exist to group related things; one item per Stash defeats the model and
clutters Discover.
"""


@prompts_app.command("agent-guidance")
def prompts_agent_guidance():
    """Print the canonical 'what is a Skill + when to create one' prompt.

    Intended for coding agents (Claude Code, Codex, Cursor, etc.) to
    re-inject when they want to remember the model mid-session."""
    console.print(AGENT_GUIDANCE_PROMPT)


if __name__ == "__main__":
    app()
