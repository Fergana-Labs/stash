"""Stash CLI — command-line interface for files, tables, sessions, and search."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shutil
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import click
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
from .client import StashClient, StashError, split_source_tokens
from .config import (
    MANIFEST_FILE,
    PRODUCTION_BASE_URL,
    Manifest,
    load_config,
    load_enabled_agents,
    load_manifest,
    save_config,
    save_enabled_agents,
    save_recorded_paths,
    save_scope,
    session_link_enabled,
    set_codex_auto_update,
    set_session_link,
    start_streaming,
    stop_streaming,
    stored_base_url,
    streaming_stopped,
)
from .exit_codes import (
    EXIT_INTERNAL_ERROR,
    EXIT_SUCCESS,
    EXIT_USER_ERROR,
    TRANSPORT_ERROR_STATUS,
    classify_error,
)
from .formatting import (
    console,
    console_err,
    echo_error,
    echo_stderr,
    output_json,
    print_empty_state,
    print_user,
)

app = typer.Typer(
    name="stash",
    help="Stash CLI — Skills, files, tables, and sessions.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"stash {__version__}")
        raise typer.Exit()


# Runtime flag for the global `stash --json` option, set eagerly by the root
# callback before the subcommand runs. Commands resolve their mode with
# _use_json(flag): the per-command --json flag ORs with this global flag.
_JSON_MODE: bool = False


def _json_callback(value: bool) -> None:
    global _JSON_MODE
    if value:
        _JSON_MODE = True


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
    json: bool = typer.Option(
        False,
        "--json",
        is_eager=True,
        callback=_json_callback,
        help=(
            "Emit machine-parseable JSON on stdout for the invoked command. "
            "All progress, status, warnings, and errors go to stderr."
        ),
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    typer.echo(ctx.get_help())
    raise typer.Exit()


@app.command()
def upgrade(
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Upgrade the stash CLI to the latest version on PyPI."""
    import subprocess

    from stashai import release

    if release.is_editable():
        _exit_user_error("This is an editable checkout — `git pull` to update it.")
    command = release.upgrade_command()
    if command is None:
        _exit_user_error(
            f"This install has no working upgrader (no uv, no pip). "
            f"Re-run the installer: {release.INSTALLER}"
        )
    echo_stderr(f"Upgrading stashai from {__version__}…")
    result = subprocess.run(command)
    if _use_json(as_json):
        output_json({"ok": result.returncode == 0, "exit_code": result.returncode})
    raise typer.Exit(result.returncode)


def _client(auto: bool = False) -> StashClient:
    """auto=True tags every request as automated housekeeping so content-
    activity analytics can exclude its reads (see auth._set_request_via)."""
    cfg = load_config()
    return StashClient(
        base_url=cfg["base_url"],
        api_key=cfg.get("api_key", ""),
        scope=cfg.get("scope", ""),
        auto=auto,
    )


def _json_mode() -> bool:
    """True when ``stash --json`` was given before the subcommand name."""
    return _JSON_MODE


def _use_json(flag) -> bool:
    """Resolve JSON mode for a command: the per-command ``--json`` flag ORs
    with the global ``stash --json`` runtime flag (STAS-060).

    ``flag is True`` (not ``bool(flag)``): a caller that invokes the command
    function directly bypasses Typer, so an unset flag arrives as a (truthy)
    OptionInfo — the same hazard the upload command guards against inline."""
    return flag is True or _json_mode()


def _emit_cli_error(status_code: int, detail, is_internal: bool = False) -> None:
    """Emit one CLI failure on stderr — the single channel for error text.

    JSON mode: a single-line structured envelope on stderr (stdout stays
    empty, so the data channel never interleaves with diagnostics). Human
    mode: the plain `Error [N]:` lines. One codepath for every failure that
    routes through _err or the main() entry boundary, so the envelope can
    never diverge between the two.
    """
    if _json_mode():
        text = detail if isinstance(detail, str) else "; ".join(str(d) for d in detail)
        envelope = json.dumps(
            {
                "error": {
                    "status_code": status_code,
                    "detail": text,
                    "class": "internal_error" if is_internal else "user_error",
                }
            }
        )
        # No-wrap: the envelope is data — a wrapped line would break the
        # single-line JSON a hook runner reads from stderr.
        console_err.print(envelope, soft_wrap=True, markup=False)
        return
    if isinstance(detail, list):
        echo_error(f"Error [{status_code}]:")
        for item in detail:
            echo_error(f"  • {item}")
    else:
        echo_error(f"Error [{status_code}]: {detail}")


def _err(e: StashError) -> None:
    _emit_cli_error(e.status_code, e.detail, is_internal=classify_error(e) == EXIT_INTERNAL_ERROR)
    raise typer.Exit(classify_error(e))


def _exit_user_error(message: str) -> None:
    """Write `message` to stderr and exit with EXIT_USER_ERROR (1)."""
    _emit_cli_error(0, message)
    raise typer.Exit(EXIT_USER_ERROR)


def _exit_internal_error(message: str) -> None:
    """Write `message` to stderr and exit with EXIT_INTERNAL_ERROR (2)."""
    _emit_cli_error(0, message, is_internal=True)
    raise typer.Exit(EXIT_INTERNAL_ERROR)


def _report_mutation(
    use_json: bool, changed: bool, message: str, markup: str | None = None
) -> None:
    """Report a mutating command's outcome under the idempotent no-op contract.

    Re-running a mutation on an already-done state is a no-op, not an error:
    this always ends with exit 0, and the no-op is reported explicitly. In
    --json mode stdout carries exactly one stable document
    {"ok": true, "changed": <bool>}; the human `message` goes to stderr so the
    re-run is visible without polluting stdout. Outside --json, a no-op prints
    `message` to stderr (a silent skip would mislead an agent into re-doing
    work); a changed run prints `markup`, or nothing when the command's own
    status lines already reported success (connect)."""
    if use_json:
        output_json({"ok": True, "changed": changed})
        echo_stderr(message)
        return
    if not changed:
        echo_stderr(message)
        return
    if markup:
        console.print(markup)


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


def _refocus_terminal() -> None:
    """Bring the user's terminal app back to the foreground after browser auth.

    The browser steals focus during sign-in, so after clicking Authorize the
    user is left staring at the done page while onboarding continues in a
    hidden terminal. On macOS every GUI terminal stamps __CFBundleIdentifier
    into its children's env, so `open -b` re-activates whichever app this CLI
    is actually running in. Elsewhere (Linux, SSH) there's no reliable way to
    grab focus, so we leave the user where they are.
    """
    import os
    import subprocess

    if sys.platform != "darwin":
        return
    bundle_id = os.environ.get("__CFBundleIdentifier")
    if not bundle_id:
        return
    subprocess.run(["open", "-b", bundle_id], check=False, capture_output=True)


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
                _refocus_terminal()
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

_SUPPORTED_AGENTS = ("claude", "cursor", "codex", "opencode", "gemini", "openclaw", "hermes", "pi")

_AGENT_BINARY = {
    "claude": "claude",
    "cursor": "cursor-agent",
    "codex": "codex",
    "opencode": "opencode",
    "gemini": "gemini",
    "openclaw": "openclaw",
    "hermes": "hermes",
    "pi": "pi",
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


def _claude_binary() -> str | None:
    """Resolve the `claude` executable, PATH first then the known install
    locations.

    PATH alone misses real installs: the local/migrate install parks the
    binary at ~/.claude/local/claude behind a *shell alias* (never on PATH,
    so `which` can never see it), and ~/.local/bin is on PATH only if a shell
    rc put it there — which a non-interactive process may not inherit.
    """
    import os

    found = shutil.which(_AGENT_BINARY["claude"])
    if found:
        return found
    home = Path.home()
    for candidate in (
        home / ".local" / "bin" / "claude",
        home / ".claude" / "local" / "claude",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _agent_present(agent: str) -> bool:
    """True if the agent is usable on this machine (binary on PATH or config dir exists)."""
    import shutil

    if agent == "claude":
        # ~/.claude is where Claude Code keeps the transcripts we record, so
        # it — not PATH — is the honest signal that this machine runs Claude
        # Code. Requiring the binary hid the flagship agent from users whose
        # install isn't on PATH, and took their history import down with it.
        return _claude_binary() is not None or (Path.home() / ".claude").is_dir()
    if shutil.which(_AGENT_BINARY[agent]):
        return True
    if agent == "codex":
        return _codex_present()
    if agent == "cursor":
        return (Path.home() / ".cursor").is_dir()
    if agent == "gemini":
        return (Path.home() / ".gemini").is_dir()
    if agent == "hermes":
        return (Path.home() / ".hermes").is_dir()
    if agent == "pi":
        return (Path.home() / ".pi").is_dir()
    # Openclaw needs its binary for `openclaw plugins install`, so a config
    # dir alone doesn't count as present.
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


def _merge_json_hooks(
    dest: Path, template: str, plugin_root: Path, markers: tuple[str, ...]
) -> str:
    """Merge stash hook entries into a JSON hooks file under each event array.

    Stash-owned entries are identified by `markers` — substrings embedded in
    their command strings — so re-runs sweep out every stash-owned entry
    (including stale ones left by old dev checkouts or prior pipx versions)
    and leave user-added entries untouched. Returns 'installed', 'skipped',
    or 'failed'.
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
        user_entries = [e for e in cur if not any(_entry_references(e, m) for m in markers)]
        merged = user_entries + tmpl_entries
        if merged != cur:
            changed = True
        existing_hooks[event] = merged

    if not changed:
        return "skipped"

    dest.write_text(json.dumps(existing, indent=2) + "\n")
    return "installed"


def _install_claude(force: bool, use_json: bool = False) -> tuple[str, str]:
    # Delegates to the canonical helper used by `stash connect`. Both
    # `claude plugin marketplace add` and `claude plugin install` are idempotent
    # so --force doesn't need to change behavior.
    ok = _install_claude_plugin(use_json)
    if ok:
        return ("installed", "claude plugin installed via marketplace")
    if _claude_binary() is None:
        return ("failed", "no `claude` executable found — see above")
    return ("failed", "claude plugin install; see inline output")


def _install_cursor(force: bool, use_json: bool = False) -> tuple[str, str]:
    root = _assets_dir("cursor")
    dest = Path.home() / ".cursor" / "hooks.json"
    template = (root / "hooks.json").read_text()
    # The second marker sweeps stale absolute-path entries written by
    # pre-`stash hook run` installs.
    status_ = _merge_json_hooks(
        dest,
        template,
        root,
        ("stash hook run cursor", "stashai/plugin/assets/cursor"),
    )
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


def _install_codex(force: bool, use_json: bool = False) -> tuple[str, str]:
    root = _assets_dir("codex")
    hooks_dest = Path.home() / ".codex" / "hooks.json"
    template = (root / "hooks.json").read_text()
    # The second marker sweeps stale absolute-path entries written by
    # pre-`stash hook run` installs.
    status_ = _merge_json_hooks(
        hooks_dest,
        template,
        root,
        ("stash hook run codex", "stashai/plugin/assets/codex"),
    )

    # One-shot cleanup: old installs wrote a top-level `_comment` key that
    # makes Codex reject the entire hooks file.
    if status_ != "failed":
        hooks_data = json.loads(hooks_dest.read_text())
        if "_comment" in hooks_data:
            del hooks_data["_comment"]
            hooks_dest.write_text(json.dumps(hooks_data, indent=2) + "\n")
            status_ = "installed"

    # Append config.toml snippet idempotently via marker line.
    from string import Template

    cfg_path = Path.home() / ".codex" / "config.toml"
    existing = cfg_path.read_text() if cfg_path.exists() else ""
    snippet = Template((root / "config.toml.snippet").read_text()).safe_substitute(
        PLUGIN_ROOT=str(root)
    )

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if _CODEX_MARKER not in existing:
        existing, snippet = _merge_snippet_into_toml(existing, snippet)
        sep = "\n" if existing and not existing.endswith("\n") else ""
        cfg_path.write_text(f"{existing}{sep}\n{_CODEX_MARKER}\n{snippet}\n")
        # Codex's workspace-write sandbox blocks outbound network, which
        # silently kills our hook uploads — recording Codex is impossible
        # without lifting it. The user chose to record Codex a question ago,
        # so state the consequence rather than asking a second, scarier
        # version of the same question.
        console.print(
            f"  [dim]Lifted the outbound-network block in Codex's workspace-write "
            f"sandbox ({cfg_path}) — its hooks can't upload without it. Delete that "
            f"block to keep the sandbox tight and launch `codex --profile stash` "
            f"instead.[/dim]"
        )

    agents_src = root / "AGENTS.md"
    agents_dest = Path.home() / ".codex" / "AGENTS.md"
    if agents_src.exists():
        _upsert_agents_md(agents_dest, agents_src.read_text())

    return (status_, f"{hooks_dest} + merged {cfg_path} + {agents_dest}")


def _install_opencode(force: bool, use_json: bool = False) -> tuple[str, str]:
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


def _install_gemini(force: bool, use_json: bool = False) -> tuple[str, str]:
    root = _assets_dir("gemini")
    dest = Path.home() / ".gemini" / "settings.json"
    template = (root / "settings.snippet.json").read_text()
    # The second marker sweeps stale absolute-path entries written by
    # pre-`stash hook run` installs.
    status_ = _merge_json_hooks(
        dest,
        template,
        root,
        ("stash hook run gemini", "stashai/plugin/assets/gemini"),
    )

    agents_dest = Path.home() / ".gemini" / "GEMINI.md"
    _upsert_agents_md(agents_dest, (root / "GEMINI.md").read_text())
    return (status_, f"{dest} + {agents_dest}")


_HERMES_MARKER_BEGIN = "# stash-plugin:begin"
_HERMES_MARKER_END = "# stash-plugin:end"
_HERMES_APPROVAL_NOTE = (
    " — Hermes asks you to approve each hook on first use "
    "(review with `hermes hooks list`; pre-approve with HERMES_ACCEPT_HOOKS=1)"
)


def _install_hermes(force: bool, use_json: bool = False) -> tuple[str, str]:
    """Wire the stash shell hooks into ~/.hermes/config.yaml.

    The hooks block lives inside a stash-owned marker-comment block so re-runs
    replace it wholesale without touching user config. We deliberately don't
    text-merge into a user-owned top-level `hooks:` key — duplicate top-level
    YAML keys are last-one-wins in PyYAML, which would silently drop hooks —
    so that case fails loud with a merge-by-hand message.
    """
    import re

    root = _assets_dir("hermes")
    cfg_path = Path.home() / ".hermes" / "config.yaml"
    snippet = (root / "config.snippet.yaml").read_text()
    block = f"{_HERMES_MARKER_BEGIN}\n{snippet.rstrip()}\n{_HERMES_MARKER_END}"

    existing = cfg_path.read_text() if cfg_path.exists() else ""

    if _HERMES_MARKER_BEGIN in existing and _HERMES_MARKER_END in existing:
        pre, rest = existing.split(_HERMES_MARKER_BEGIN, 1)
        _, post = rest.split(_HERMES_MARKER_END, 1)
        new = f"{pre}{block}{post}"
        if new == existing and not force:
            return ("skipped", f"{cfg_path} already wired")
        cfg_path.write_text(new)
        return ("installed", f"{cfg_path} (stash hooks block refreshed){_HERMES_APPROVAL_NOTE}")

    if re.search(r"^hooks\s*:", existing, flags=re.MULTILINE):
        return (
            "failed",
            f"{cfg_path} already has a top-level hooks: block; add the entries from "
            f"{root / 'config.snippet.yaml'} to it by hand",
        )

    sep = "" if not existing or existing.endswith("\n") else "\n"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(f"{existing}{sep}{block}\n")
    return ("installed", f"{cfg_path}{_HERMES_APPROVAL_NOTE}")


def _openclaw_extension_dir() -> Path:
    return Path.home() / ".openclaw" / "extensions" / "stash"


def _dir_content_matches(src: Path, dest: Path) -> bool:
    """True if every file under src exists with identical bytes under dest.
    Extra files in dest (node_modules, state) don't count as drift."""
    for path in src.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        other = dest / path.relative_to(src)
        if not other.is_file() or other.read_bytes() != path.read_bytes():
            return False
    return True


_OPENCLAW_MIN_VERSION = (2026, 4, 0)


def _install_openclaw(force: bool, use_json: bool = False) -> tuple[str, str]:
    import subprocess

    root = _assets_dir("openclaw")
    ext_dir = _openclaw_extension_dir()
    if ext_dir.is_dir() and _dir_content_matches(root, ext_dir):
        return ("skipped", f"{ext_dir}")

    # The stash extension needs openclaw >= 2026.4.0 (its plugin-sdk layout
    # and the install flags below). Older CLIs die with "unknown option
    # '--force'", which tells the user nothing — name the real problem.
    version_out = subprocess.run(
        ["openclaw", "--version"], capture_output=True, text=True, timeout=30
    )
    match = re.search(r"\b(\d{4})\.(\d+)\.(\d+)\b", version_out.stdout)
    if match:
        version = tuple(int(g) for g in match.groups())
        if version < _OPENCLAW_MIN_VERSION:
            installed = ".".join(str(v) for v in version)
            needed = ".".join(str(v) for v in _OPENCLAW_MIN_VERSION)
            return (
                "failed",
                f"openclaw {installed} is older than {needed}, which the stash "
                "extension needs — upgrade openclaw, then re-run stash setup",
            )

    # --dangerously-force-unsafe-install: openclaw's code scanner blocks any
    # plugin that spawns processes, and piping hook events into the stashai
    # Python scripts via child_process is this extension's whole mechanism.
    result = subprocess.run(
        [
            "openclaw",
            "plugins",
            "install",
            "--force",
            "--dangerously-force-unsafe-install",
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        return ("failed", tail[-1] if tail else "openclaw plugins install failed")
    return (
        "installed",
        f"{ext_dir} (restart the gateway to load it: `openclaw gateway restart`)",
    )


def _copy_pi_runtime(scripts_src: Path, dest: Path, force: bool) -> bool:
    """Copy the pi hook runtime from the shipped assets into ~/.pi/.

    Each hook wrapper execs "$SCRIPT_DIR/../_run.sh" and _run.sh resolves its
    handler via "TARGET=$SCRIPT_DIR/$SCRIPT.py", so the whole scripts/ tree maps
    1:1 onto ~/.pi/: scripts/_run.sh -> ~/.pi/_run.sh, scripts/hooks/* ->
    ~/.pi/hooks/*, and scripts/on_*.py|config.py|adapt.py -> ~/.pi/. We copy
    bytes (never symlink) so the install stays self-contained even if the
    checkout or pipx env moves. Returns True if anything was written.
    """
    import shutil

    changed = False
    for src in sorted(scripts_src.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(scripts_src)
        dst = dest / rel
        # A pre-existing symlink (e.g. from an older symlink installer) still
        # points at the repo — replace it with a real copy so the install stays
        # self-contained and carries no absolute shipped-assets path.
        if dst.is_symlink():
            dst.unlink()
        if dst.exists() and dst.read_bytes() == src.read_bytes() and not force:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        shutil.copymode(src, dst)  # keep hooks / _run.sh executable
        changed = True
    return changed


def _install_pi(force: bool, use_json: bool = False) -> tuple[str, str]:
    root = _assets_dir("pi")
    dest = Path.home() / ".pi"
    agents_dest = dest / "AGENTS.md"

    changed = _copy_pi_runtime(root / "scripts", dest, force)

    # Install AGENTS.md via the existing idempotent helper
    agents_src = root / "AGENTS.md"
    if agents_src.exists():
        _upsert_agents_md(agents_dest, agents_src.read_text())

    if not changed and not force:
        return ("skipped", f"{dest} already up to date + {agents_dest}")
    return ("installed", f"copied pi runtime \u2192 {dest} + {agents_dest}")


_INSTALLERS = {
    "claude": _install_claude,
    "cursor": _install_cursor,
    "codex": _install_codex,
    "opencode": _install_opencode,
    "gemini": _install_gemini,
    "openclaw": _install_openclaw,
    "hermes": _install_hermes,
    "pi": _install_pi,
}


# ===========================================================================
# Hook plumbing — invoked by coding agents, not interactively
# ===========================================================================

hook_app = typer.Typer(help="Hook plumbing invoked by coding agents. Not for interactive use.")
app.add_typer(hook_app, name="hook", hidden=True)

_HOOK_EVENTS = {
    "claude": ("on_session_start", "on_prompt", "on_tool_use", "on_stop", "on_session_end"),
    "codex": ("on_session_start", "on_prompt", "on_tool_use", "on_stop"),
    "cursor": (
        "on_session_start",
        "on_prompt",
        "on_tool_use",
        "on_agent_response",
        "on_session_end",
    ),
    "gemini": ("on_session_start", "on_prompt", "on_tool_use", "on_stop", "on_session_end"),
    "hermes": ("on_session_start", "on_prompt", "on_tool_use", "on_stop", "on_session_end"),
    "openclaw": ("on_session_start", "on_prompt", "on_stop", "on_session_end"),
    "opencode": ("on_session_start", "on_prompt", "on_tool_use", "on_session_end"),
}


@hook_app.command("run")
def hook_run(
    agent: str = typer.Argument(...),
    event: str = typer.Argument(...),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run a plugin hook script. Reads the agent's JSON payload on stdin.

    Agent hook files reference this command so every hook runs the scripts
    shipped inside the installed stashai package, under the package's own
    interpreter — no venv hunting, no version skew between scripts and
    library. The command is also byte-identical across upgrades, which is
    what keeps Codex (which trusts hooks by command hash) from silently
    distrusting the hooks after a stash/python upgrade.
    """
    events = _HOOK_EVENTS.get(agent)
    if events is None:
        _exit_user_error(f"Unknown hook agent: {agent}")
    if event not in events:
        _exit_user_error(f"Unknown {agent} hook event: {event}")

    import runpy

    script = _assets_dir(agent) / "scripts" / f"{event}.py"
    sys.path.insert(0, str(script.parent))
    runpy.run_path(str(script), run_name="__main__")


@hook_app.command("auto-update")
def hook_auto_update(
    choice: str = typer.Argument(..., help="'on' or 'off'"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Record whether Stash may auto-update at Codex session start."""
    if choice not in ("on", "off"):
        _exit_user_error("Pass 'on' or 'off'.")
    set_codex_auto_update(choice == "on")
    if _use_json(as_json):
        output_json({"ok": True, "autoupdate": choice == "on", "choice": choice})
        return
    console.print(f"Codex auto-update {choice}.")


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
    if agent == "gemini":
        settings_path = Path.home() / ".gemini" / "settings.json"
        if not settings_path.exists():
            return False
        try:
            return "stashai/plugin/assets/gemini" in settings_path.read_text()
        except OSError:
            return False
    if agent == "openclaw":
        return _openclaw_extension_dir().is_dir()
    if agent == "hermes":
        cfg_path = Path.home() / ".hermes" / "config.yaml"
        if not cfg_path.exists():
            return False
        try:
            return "stashai/plugin/assets/hermes" in cfg_path.read_text()
        except OSError:
            return False
    if agent == "pi":
        # The self-contained marker _install_pi leaves behind: the native hook
        # dir plus the _run.sh interpreter-resolution runtime both exist.
        return (Path.home() / ".pi" / "hooks").is_dir() and (
            Path.home() / ".pi" / "_run.sh"
        ).exists()
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
    if not skills:
        print_empty_state("public skills matching your filters")
    if _use_json(as_json):
        output_json(skills)
        return

    if not skills:
        return

    if not pick:
        for skill in skills:
            owner = skill.get("owner_display_name") or skill.get("owner_name") or "unknown"
            console.print(
                f"[bold]{skill['title']}[/bold]  [dim]by {owner}[/dim]  "
                f"{skill['item_count']} items, {skill['view_count']} views"
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
                    f"{picked['item_count']} items, {picked['view_count']} views",
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


def _resolve_session(handle: str, field: str = "session_id") -> str:
    """Session titles are aliases for session ids across the CLI.

    A handle matching a session title — the stored spelling, the VFS
    safe_name spelling that `stash search` prints, or the `/sessions/<name>`
    directory name that `stash vfs ls` prints — resolves to that session's
    `field`: "session_id" (the transcript stream id) or "id" (the row id
    `rm`/`restore`/`mv`/`shares` take). Anything else is already an id and
    passes through untouched; the server rejects unknown ids loudly.

    The matching itself is server-side, so the CLI, the MCP tools, and the VFS
    cannot disagree about what a name means."""
    return _resolved_session_field(handle, field, trashed=False)


def _resolve_trashed_session(handle: str) -> str:
    """The row id of a trashed session named by title, for `stash restore`.

    A trashed session is gone from the scope listing, so its title resolves
    against the trash — the same set `stash trash list` prints."""
    return _resolved_session_field(handle, "id", trashed=True)


def _resolved_session_field(handle: str, field: str, *, trashed: bool) -> str:
    with _client() as c:
        try:
            return c.resolve_session(handle, trashed=trashed)[field]
        except StashError as e:
            _err(e)


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
        "", "--session", "-s", help="Session ID or title. Auto-detected if omitted."
    ),
    files: list[str] = typer.Option([], "--file", "-f", help="Files to attach (repeatable)."),
    as_json: bool = typer.Option(
        False, "--json", help="Emit a machine-parseable result object on stdout."
    ),
):
    """Share a session as a public Skill.

    Publishes a focused summary (the question + finding), the full conversation
    transcript, and any attached files as a single public Skill.
    """
    use_json = _use_json(as_json)

    def status(markup: str, plain: str) -> None:
        # Progress/status goes to stderr in JSON mode so stdout stays a single
        # JSON document; default mode keeps it on stdout (original behavior).
        if use_json:
            echo_stderr(plain)
        else:
            console.print(markup)

    _require_auth()
    telemetry.record("share")

    # Resolve session ID
    sid = _resolve_session(session_id) if session_id else _current_session_id()
    if not sid:
        _exit_user_error("Could not detect session. Pass --session <id or title> explicitly.")

    # Find and read the JSONL transcript
    jsonl_path = _find_session_jsonl(sid)
    if not jsonl_path:
        _exit_user_error(f"Transcript file not found for session {sid[:8]}…")

    raw_jsonl = jsonl_path.read_text(errors="replace")
    ai_title, first_user, last_assistant = _extract_session_bookends(raw_jsonl)

    if not last_assistant:
        _exit_user_error("No assistant messages found in this session.")

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

    status(f"[dim]Sharing session {sid[:8]}…[/dim]", f"Sharing session {sid[:8]}…")

    with _client() as c:
        # Create a folder for this session, then drop Summary + Full Transcript inside.
        folder = c.create_folder(page_title)
        c.create_page("Summary", content=summary_md, folder_id=folder["id"])
        c.create_page("Full Transcript", content=full_md, folder_id=folder["id"])

        for sa_label, sa_raw, _sa_path in subagent_entries:
            sa_md = _transcript_to_markdown(sa_raw)
            c.create_page(f"Subagent: {sa_label}", content=sa_md, folder_id=folder["id"])
            status(
                f"  [dim]Included subagent: {sa_label}[/dim]", f"  Included subagent: {sa_label}"
            )

        # Upload attached files into the session folder
        for fp in files:
            p = Path(fp)
            if not p.exists():
                echo_stderr(f"Skipping {fp} (not found)")
                continue
            c.upload_file(str(p), folder_id=folder["id"])
            status(f"  [dim]Attached {p.name}[/dim]", f"  Attached {p.name}")

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
    if use_json:
        output_json(
            {
                "ok": True,
                "url": public_url,
                "folder_id": folder["id"],
                "title": page_title,
            }
        )
        return
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


# Mirrors backend files_tree_service.HTML_EXTS — these become HTML pages
# server-side, so the CLI must not pre-empt that by posting them as markdown.
_HTML_UPLOAD_EXTENSIONS = {".html", ".htm"}


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
    public_link: bool = typer.Option(
        False,
        "--public-link",
        help=(
            "Give the upload an 'anyone with the link' grant, so the returned "
            "app_url opens for people you send it to. Without this an upload "
            "is private and its link works only for you."
        ),
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Upload a local file or directory into your Files.

    A single file lands directly in your Files (Markdown/HTML become
    editable pages, everything else a binary file). A directory becomes a folder, and
    every text file in it — Markdown, HTML, code, CSV, and friends —
    becomes an editable page. **No Skill is created.**

    Uploads are private. The returned ``app_url`` opens for you alone unless
    you pass ``--public-link``, which adds an "anyone with the link" grant —
    that is what makes the URL worth handing to someone else.

    Pass ``--skill <title>`` to *also* bundle the upload into a shareable
    Skill. Use a Skill when you're publishing a folder of related
    artifacts (a project writeup with its supporting files, a research
    thread with its sources) — not as a wrapper around every single
    upload."""
    _require_auth()
    telemetry.record("upload")
    # Callers that invoke this function directly bypass Typer's default
    # resolution, so an unset flag arrives as a (truthy) OptionInfo. Publishing
    # someone's upload to anyone-with-the-link is not a mistake we can make by
    # accident, so nothing short of a literal True counts.
    public_link = public_link is True
    use_json = _use_json(as_json)
    if use_json:

        def status(markup: str, plain: str) -> None:
            echo_stderr(plain)
    else:

        def status(markup: str, plain: str) -> None:
            console.print(markup)

    target = Path(path)
    if not target.exists():
        _exit_user_error(f"Not found: {path}")

    # A single file with no Skill goes straight into Files — no wrapping
    # folder. The server routes Markdown/HTML to pages.
    if target.is_file() and not skill:
        with _client() as c:
            try:
                data = _upload_path(c, str(target))
                if public_link:
                    c.set_general_access(data["kind"], data["id"], "read")
                    # An HTML page's pictures are separate file rows; without
                    # their own grant the shared page shows broken images.
                    for asset_id in data.get("asset_file_ids") or []:
                        c.set_general_access("file", asset_id, "read")
            except StashError as e:
                _err(e)
        data["public_link"] = public_link
        if _use_json(as_json):
            output_json(data)
            return
        label = "Uploaded as page" if data.get("kind") == "page" else "Uploaded"
        console.print(f"[green]{label}[/green] {data['name']}  [dim]{data['id']}[/dim]")
        console.print(data["app_url"])
        if not public_link:
            console.print(
                "[dim]Private — only you can open that link. "
                "Re-run with --public-link to share it.[/dim]"
            )
        return

    files = _upload_file_list(target)
    if not files:
        _exit_user_error(f"No files found in {path}")

    root_name = name or (target.stem if target.is_file() else target.name)
    skill_title = skill.strip() or root_name
    create_skill = bool(skill)
    status(
        f"[dim]Uploading {len(files)} file(s) as '{root_name}'...[/dim]",
        f"Uploading {len(files)} file(s) as '{root_name}'...",
    )

    with _client() as c:
        root_folder = c.create_folder(root_name)
        folder_cache: dict[tuple[str, str], str] = {}

        # HTML last: by then every sibling picture has been uploaded, so the
        # markup can be rewritten to point at those files instead of re-
        # uploading them.
        asset_urls: dict[Path, str] = {}
        html_files = [f for f in files if f.suffix.lower() in _HTML_UPLOAD_EXTENSIONS]
        for file_path in [f for f in files if f not in html_files] + html_files:
            relative_path = (
                file_path.relative_to(target) if target.is_dir() else Path(file_path.name)
            )
            folder_id = _upload_folder_for_file(
                c,
                root_folder["id"],
                folder_cache,
                relative_path,
            )

            # HTML goes through the server's ingest, which files it as an HTML
            # page. Reading it here and posting it as `content` would store the
            # markup in the markdown field, where it renders as escaped source
            # instead of a page — the same file uploaded on its own renders
            # correctly, and that inconsistency is the bug.
            if file_path in html_files:
                _upload_html_with_assets(c, file_path, folder_id, asset_urls)
                status(f"  [dim]Page: {relative_path}[/dim]", f"  Page: {relative_path}")
                continue

            if _is_upload_text_file(file_path):
                content = file_path.read_text(errors="replace")
                c.create_page(file_path.name, content=content, folder_id=folder_id)
                status(f"  [dim]Page: {relative_path}[/dim]", f"  Page: {relative_path}")
                continue

            # Creating the stub page embeds the binary: the server claims any
            # root file whose download link appears in a saved page body.
            uploaded = c.upload_file(str(file_path))
            asset_urls[file_path.resolve()] = f"/api/v1/me/files/{uploaded['id']}/download"
            c.create_page(
                file_path.name,
                content=_markdown_snippet(uploaded),
                folder_id=folder_id,
            )
            status(f"  [dim]File: {relative_path}[/dim]", f"  File: {relative_path}")

        folder_url = f"{_web_app_url()}/folders/{root_folder['id']}"
        result: dict = {"folder": root_folder, "app_url": folder_url}
        if public_link:
            # Folder shares cascade to their contents at read time, so one
            # grant on the root covers every page and file just uploaded.
            c.set_general_access("folder", root_folder["id"], "read")
            result["public_link"] = True

        if create_skill:
            # Skill membership is a stored flag: writing a SKILL.md does not
            # make a folder a skill, the convert verb does.
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
            c.convert_folder_to_skill(root_folder["id"])
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Download your entire Stash as a zip of standard files.

    Folders become directories, pages become plain .md/.html files, and
    uploads keep their original bytes — no proprietary formats, no lock-in."""
    _require_auth()
    telemetry.record("export")
    use_json = _use_json(as_json)
    destination = (
        Path(output) if output else Path(f"stash-export-{time.strftime('%Y%m%d-%H%M%S')}.zip")
    )
    if use_json:
        echo_stderr("Packaging your Stash…")
    else:
        console.print("[dim]Packaging your Stash…[/dim]")
    with _client() as c:
        try:
            data = c.export_zip()
        except StashError as e:
            _err(e)
    destination.write_bytes(data)
    if use_json:
        output_json({"ok": True, "path": str(destination), "bytes": len(data)})
        return
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Read a public Skill and print its contents."""
    slug = _parse_skill_slug(url)
    with _client() as c:
        text = c.get_skill_text(slug)
    if _use_json(as_json):
        output_json({"content": text})
        return
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Upload a local skill folder (must contain a SKILL.md) into your Files."""
    src = Path(folder)
    if not src.is_dir():
        _exit_user_error(f"Not a folder: {folder}")
    skill_md_path = src / "SKILL.md"
    if not skill_md_path.exists():
        _exit_user_error(f"Missing SKILL.md in {folder}")

    folder_name = src.name
    with _client() as c:
        try:
            # A skill is a folder marked as one; its markdown pages (SKILL.md
            # plus siblings) are its content.
            new_folder = c.create_folder(folder_name)
            folder_id = new_folder["id"]
            for md_file in sorted(src.glob("*.md")):
                c.create_page(
                    name=md_file.name,
                    content=md_file.read_text(),
                    folder_id=folder_id,
                    content_type="markdown",
                )
            c.convert_folder_to_skill(folder_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "folder_id": folder_id, "name": folder_name})
        return
    console.print(f"[green]Added skill '{folder_name}' to your Files.[/green]")


@skills_app.command("create")
def skills_create(
    name: str = typer.Argument(..., help="Skill name (becomes the folder name)."),
    description: str = typer.Option(..., "--description"),
    public: bool = typer.Option(False, "--public", help="Publish immediately."),
    discover: bool = typer.Option(False, "--discover", help="List the public Skill in Discover."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a skill: a folder with a SKILL.md template. Pass --public to publish."""
    if discover and not public:
        console.print("[red]--discover requires --public.[/red]")
        raise typer.Exit(1)
    name = name.strip()
    description = description.strip()
    if not name or len(name) > 64:
        console.print("[red]Error:[/red] skill name must contain 1-64 characters.")
        raise typer.Exit(1)
    if not description or len(description) > 1024:
        console.print("[red]Error:[/red] skill description must contain 1-1024 characters.")
        raise typer.Exit(1)
    skill_md = (
        f"---\nname: {json.dumps(name)}\ndescription: {json.dumps(description)}\n---\n\n# {name}\n"
    )
    with _client() as c:
        try:
            folder = c.create_folder(name)
            c.create_page(
                name="SKILL.md",
                content=skill_md,
                folder_id=folder["id"],
                content_type="markdown",
            )
            # Membership is a stored flag; the SKILL.md above is the skill's
            # instructions, not what makes the folder a skill.
            c.convert_folder_to_skill(folder["id"])
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
    """Update a published skill's metadata or Discover flag."""
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
    flag = "[cyan]discover[/cyan]" if skill.get("discoverable") else "[cyan]public[/cyan]"
    console.print(f"[green]Updated Skill[/green] '{skill['title']}'  {flag}")


@skills_app.command("unpublish")
def skills_unpublish(
    skill_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")
):
    """Stop sharing a skill: delete its publish record. The folder stays."""
    with _client() as c:
        try:
            c.unpublish_skill(skill_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "skill_id": skill_id})
        return
    console.print(f"[green]Unpublished Skill[/green] {skill_id}")


def _safe_skill_dirname(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-() ]+", "-", name).strip(" .")
    return cleaned or "skill"


def _validate_skill_markdown(markdown: str) -> None:
    if not markdown.startswith("---\n") or "\n---" not in markdown[4:]:
        raise ValueError("SKILL.md must start with YAML frontmatter")
    raw = markdown[4 : markdown.find("\n---", 4)]
    metadata = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            value = value.strip()
            metadata[key.strip()] = json.loads(value) if value.startswith('"') else value
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    if not name:
        raise ValueError("SKILL.md frontmatter requires a nonblank name")
    if len(name) > 64:
        raise ValueError("SKILL.md name must be at most 64 characters")
    if not description:
        raise ValueError("SKILL.md frontmatter requires a nonblank description")
    if len(description) > 1024:
        raise ValueError("SKILL.md description must be at most 1024 characters")


def _validate_skill_contents(contents: dict) -> None:
    skill_pages = [
        page for page in contents["pages"] if page["name"] == "SKILL.md" and not page["folder_path"]
    ]
    if len(skill_pages) != 1:
        raise ValueError("skill must contain one root SKILL.md")
    _validate_skill_markdown(skill_pages[0]["content_markdown"] or "")


def _materialize_skill(detail: dict, skills_root: Path, fetch_bytes) -> tuple[Path, int]:
    """Write a public-skill payload to skills_root/<folder_name>.

    Returns (target_dir, items_written). fetch_bytes(url) -> bytes is
    injected so tests don't hit the network. Replacing an existing install
    is allowed only when the target already looks like a skill (has a
    SKILL.md) — never delete an arbitrary directory on a name collision."""
    contents = detail["contents"]
    _validate_skill_contents(contents)
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


# --- installed-skill manifest: Discover/shared installs that auto-update ---
#
# Owned skills sync through the three-way state below; skills the user
# INSTALLED (someone else's, by slug or share) are tracked here instead.
# `stash skills sync` — which the plugin spawns at session start — refreshes
# every manifest entry whose cloud copy changed, so installs stay current
# without the user re-running install.


def _installed_manifest_path() -> Path:
    return Path.home() / ".stash" / "installed_skills.json"


def _load_installed_manifest() -> dict:
    path = _installed_manifest_path()
    return json.loads(path.read_text()) if path.exists() else {}


def _save_installed_manifest(manifest: dict) -> None:
    path = _installed_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1))


def _installed_entry(manifest: dict, root: Path) -> dict:
    return manifest.setdefault(str(root.resolve()), {"skills": {}, "follow_shared": False})


def _skills_root(directory: str, project: bool) -> Path:
    if directory and project:
        console.print("[red]Error:[/red] pass either --dir or --project, not both.")
        raise typer.Exit(1)
    if directory:
        return Path(directory).expanduser()
    if project:
        return Path(".claude") / "skills"
    return Path.home() / ".claude" / "skills"


def _fetch_bytes(url: str) -> bytes:
    resp = httpx.get(url, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    return resp.content


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
    available to the agent from its next session. Installed skills are
    tracked and auto-update whenever `stash skills sync` runs (the plugin
    runs one at every session start); `stash skills uninstall` removes one.
    """
    root = _skills_root(directory, project)

    with _client() as c:
        try:
            detail = c.get_public_skill(slug)
            target, written = _materialize_skill(detail, root, _fetch_bytes)
        except StashError as e:
            _err(e)
        except ValueError as e:
            console.print(f"[red]Invalid skill:[/red] {e}")
            raise typer.Exit(1) from e
        # Adoption ping — best-effort: a metrics hiccup must not fail an
        # install that already succeeded on disk.
        try:
            c.record_skill_install(slug)
        except (StashError, httpx.HTTPError):
            pass

    manifest = _load_installed_manifest()
    _installed_entry(manifest, root)["skills"][target.name] = {
        "slug": slug,
        "remote_hash": _hash_remote_contents(detail["contents"]),
    }
    _save_installed_manifest(manifest)

    if _use_json(as_json):
        output_json({"path": str(target), "items": written})
        return
    console.print(
        f"[green]Installed[/green] '{detail['skill']['title']}' → {target}  ({written} items)"
    )
    console.print(
        "[dim]The agent loads it at its next session start; "
        "it auto-updates on `stash skills sync`.[/dim]"
    )


@skills_app.command("uninstall")
def skills_uninstall(
    name: str = typer.Argument(..., help="Installed skill's slug or folder name."),
    directory: str = typer.Option("", "--dir", help="Skills directory the skill lives in."),
    project: bool = typer.Option(
        False, "--project", help="Uninstall from ./.claude/skills (this repo only)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Remove an installed Skill and stop auto-updating it."""
    root = _skills_root(directory, project)
    manifest = _load_installed_manifest()
    entry = _installed_entry(manifest, root)
    match = next(
        (n for n, rec in entry["skills"].items() if name in (n, rec.get("slug"))),
        None,
    )
    if match is None:
        _exit_user_error(f"'{name}' is not an installed skill in {root}.")

    target = root / match
    if target.exists():
        if not (target / "SKILL.md").exists():
            _exit_user_error(f"{target} doesn't look like a skill folder; not deleting.")
        shutil.rmtree(target)
    del entry["skills"][match]
    _save_installed_manifest(manifest)
    if _use_json(as_json):
        output_json({"ok": True, "name": match, "root": str(root)})
        return
    console.print(f"[green]Uninstalled[/green] {match}")


@skills_app.command("list")
def skills_list(
    installed: bool = typer.Option(
        False, "--installed", help="Show locally installed skills instead of your own."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """List your skills, or locally installed ones with --installed."""
    if installed:
        manifest = _load_installed_manifest()
        rows = [
            {
                "name": skill_name,
                "root": root,
                "slug": rec.get("slug"),
                "shared_folder_id": rec.get("shared_folder_id"),
            }
            for root, entry in manifest.items()
            for skill_name, rec in entry["skills"].items()
        ]
        if not rows:
            print_empty_state("installed skills")
        if _use_json(as_json):
            output_json({"installed": rows})
            return
        for r in rows:
            source = r["slug"] or "(shared with you)"
            console.print(f"  [bold]{r['name']}[/bold]  [dim]{source} → {r['root']}[/dim]")
        return

    with _client() as c:
        try:
            skills = c.list_skills()
        except StashError as e:
            _err(e)
    if not skills:
        print_empty_state("skills")
    if _use_json(as_json):
        output_json({"skills": skills})
        return
    for s in skills:
        flags = []
        if s.get("slug"):
            flags.append(f"[cyan]{_web_app_url()}/skills/{s['slug']}[/cyan]")
        console.print(f"  [bold]{s.get('name') or s.get('title')}[/bold]  {' '.join(flags)}")


@skills_app.command("follow")
def skills_follow(
    directory: str = typer.Option("", "--dir", help="Skills directory new shares install into."),
    project: bool = typer.Option(
        False, "--project", help="Install new shares into ./.claude/skills (this repo only)."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Auto-install skills people share with you.

    New shared skills land at the next `stash skills sync` (the plugin runs
    one at every session start) and update like any installed skill.

    Idempotent: if this root already follows, the command exits 0 and reports
    the no-op without re-writing the installed manifest.
    """
    root = _skills_root(directory, project)
    use_json = _use_json(as_json)
    manifest = _load_installed_manifest()
    if _installed_entry(manifest, root).get("follow_shared"):
        _report_mutation(use_json, False, f"Already following shared skills → {root}.")
        return
    _installed_entry(manifest, root)["follow_shared"] = True
    _save_installed_manifest(manifest)
    _report_mutation(
        use_json,
        True,
        f"Following skills shared with you → {root}.",
        markup=f"[green]Following[/green] skills shared with you → {root}",
    )


@skills_app.command("unfollow")
def skills_unfollow(
    directory: str = typer.Option("", "--dir", help="Skills directory to stop following into."),
    project: bool = typer.Option(False, "--project", help="Stop following for ./.claude/skills."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Stop auto-installing newly shared skills (already-installed ones stay).

    Idempotent: a root that does not follow already has nothing to stop —
    the command exits 0 and reports the no-op.
    """
    root = _skills_root(directory, project)
    use_json = _use_json(as_json)
    manifest = _load_installed_manifest()
    if not _installed_entry(manifest, root).get("follow_shared"):
        _report_mutation(use_json, False, f"Not following shared skills → {root}.")
        return
    _installed_entry(manifest, root)["follow_shared"] = False
    _save_installed_manifest(manifest)
    _report_mutation(
        use_json,
        True,
        f"Unfollowed shared skills for {root}.",
        markup=f"[green]Unfollowed[/green] shared skills for {root}",
    )


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


def _sync_skills(
    c, root: Path, state: dict, push_new: bool, fetch_bytes, skip: set[str] = frozenset()
) -> tuple[dict, dict]:
    """Three-way sync between root and your skills.

    state maps skill folder name -> {folder_id, local_hash, remote_hash}
    captured at the last sync; comparing each side against it tells us which
    side moved. Both moved -> conflict, skipped loudly. `skip` names local
    dirs owned by the installed-skill manifest — they must never be treated
    as local-only skills (project mode would push someone else's skill into
    your Stash). Returns (summary, new_state)."""
    remote: dict[str, dict] = {}
    for s in c.list_skills():
        detail = c.get_skill_contents(s["folder_id"])
        remote[detail["folder_name"]] = detail

    local = _local_skill_dirs(root)
    summary: dict = {"pulled": [], "pushed": [], "conflicts": [], "ignored": [], "unchanged": []}
    new_state: dict = {}

    for name in sorted(set(remote) & set(skip)):
        summary["conflicts"].append(
            f"{name} (an installed skill shadows your own skill of the same name; "
            "uninstall or rename one)"
        )

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
        _validate_skill_markdown((local[name] / "SKILL.md").read_text())
        c.replace_skill_contents(folder_id, _collect_local_files(local[name]))
        record(name, c.get_skill_contents(folder_id))
        summary["pushed"].append(name)

    for name in sorted((set(remote) | set(local)) - set(skip)):
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
        except (StashError, ValueError) as e:
            detail = e.detail if isinstance(e, StashError) else str(e)
            summary["conflicts"].append(f"{name} (sync failed: {detail})")
            if rec:
                new_state[name] = rec
    return summary, new_state


def _sync_installed(c, root: Path, entry: dict, fetch_bytes) -> tuple[list[str], list[str]]:
    """Refresh manifest-tracked installed skills whose cloud copy changed,
    and install newly shared skills when this root follows shares. Mutates
    `entry` in place; returns (updated names, notes)."""
    updated: list[str] = []
    notes: list[str] = []
    skills = entry["skills"]

    if entry.get("follow_shared"):
        known = {rec.get("shared_folder_id") for rec in skills.values()}
        for shared in c.list_shared_skills():
            if shared["folder_id"] in known:
                continue
            detail = c.get_shared_skill_contents(shared["folder_id"])
            name = _safe_skill_dirname(detail["folder_name"])
            if name in skills or (root / name).exists():
                notes.append(f"{name} (new shared skill collides with an existing dir; skipped)")
                continue
            try:
                target, _written = _materialize_skill(detail, root, fetch_bytes)
            except ValueError as e:
                notes.append(f"{name} (invalid skill: {e})")
                continue
            skills[target.name] = {
                "shared_folder_id": shared["folder_id"],
                "remote_hash": _hash_remote_contents(detail["contents"]),
            }
            updated.append(f"{target.name} (newly shared)")

    for name, rec in sorted(skills.items()):
        try:
            if rec.get("slug"):
                detail = c.get_public_skill(rec["slug"])
            else:
                detail = c.get_shared_skill_contents(rec["shared_folder_id"])
        except StashError as e:
            notes.append(f"{name} (fetch failed: {e.detail})")
            continue
        remote_hash = _hash_remote_contents(detail["contents"])
        if remote_hash == rec.get("remote_hash") and (root / name).is_dir():
            continue
        try:
            target, _written = _materialize_skill(detail, root, fetch_bytes)
        except ValueError as e:
            notes.append(f"{name} (invalid skill: {e})")
            continue
        if target.name != name:
            # Renamed in the cloud: the old dir is superseded by the new one.
            old = root / name
            if (old / "SKILL.md").exists():
                shutil.rmtree(old)
            del skills[name]
        skills[target.name] = {**rec, "remote_hash": remote_hash}
        updated.append(target.name)
    return updated, notes


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
    Installed skills (from `stash skills install` or a followed share) are
    refreshed from their cloud copy instead of three-way synced.
    """
    root = _skills_root(directory, project)

    state_path = _sync_state_path(root)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    manifest = _load_installed_manifest()
    installed = _installed_entry(manifest, root)

    # Sync reads every skill's contents to compare hashes — housekeeping, not
    # someone reading a document, so its requests are tagged auto.
    with _client(auto=True) as c:
        try:
            summary, new_state = _sync_skills(
                c,
                root,
                state,
                push_new=project,
                fetch_bytes=_fetch_bytes,
                skip=set(installed["skills"]),
            )
            updated, notes = _sync_installed(c, root, installed, _fetch_bytes)
        except StashError as e:
            _err(e)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, indent=1))
    _save_installed_manifest(manifest)
    summary["updated"] = updated
    summary["ignored"] += notes

    if updated:
        # The plugin's SessionStart hook shows this list once next session, so
        # background syncs never change the skills dir invisibly.
        notice_path = _SYNC_STATE_DIR / "pending_updates.json"
        pending = json.loads(notice_path.read_text()) if notice_path.exists() else []
        notice_path.parent.mkdir(parents=True, exist_ok=True)
        notice_path.write_text(json.dumps(sorted(set(pending) | set(updated))))

    if _use_json(as_json):
        output_json(summary)
        return
    for name in summary["pulled"]:
        console.print(f"[green]pulled[/green]  {name}")
    for name in summary["pushed"]:
        console.print(f"[green]pushed[/green]  {name}")
    for name in summary["updated"]:
        console.print(f"[green]updated[/green] {name}")
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


@files_app.command("read-page")
def files_read_page(
    page_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")
):
    """Print a page as JSON. Its content_hash is what a later edit-page
    --expected-content-hash must carry."""
    with _client() as c:
        try:
            data = c.get_page(page_id)
        except StashError as e:
            _err(e)
    output_json(data)


@files_app.command("edit-page")
def files_edit_page(
    page_id: str = typer.Argument(...),
    content: str = typer.Option(None, "--content"),
    expected_content_hash: str = typer.Option(
        None,
        "--expected-content-hash",
        help="The content_hash from the read this edit is based on "
        "(`stash files read-page`). Required with --content: if the page "
        "changed since that read, the edit is refused instead of "
        "overwriting the newer version.",
    ),
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
        # Empty stdin means "no content given", not "clear the page" — a
        # scripted rename must not slurp a blank pipe as the new content.
        content = sys.stdin.read() or None
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
                if content is None:
                    # This flow reads the page itself, so that read is the
                    # version the edit is based on.
                    current = c.get_page(page_id)
                    base = current.get("content_markdown", "")
                    if expected_content_hash is None:
                        expected_content_hash = current.get("content_hash")
                else:
                    base = content
                content = _prepend_attachments(c, base, attach)
            elif attach:
                console.print("[yellow]--attach is ignored for html pages[/yellow]")
            if content is not None and expected_content_hash is None:
                console.print(
                    "[red]--content requires --expected-content-hash: pass the "
                    "content_hash from `stash files read-page` so a concurrent "
                    "edit is refused instead of overwritten.[/red]"
                )
                raise typer.Exit(1)
            kwargs: dict = {}
            if content is not None:
                kwargs["content"] = content
                kwargs["expected_content_hash"] = expected_content_hash
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
    if not data:
        print_empty_state("sessions")
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
    if not data:
        print_empty_state("agents")
    if _use_json(as_json):
        output_json(data)
    else:
        for name in data:
            console.print(f"  {name}")


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


def _stream_turn(events, collect: bool = False) -> tuple[str | None, str]:
    """Render a turn's SSE events live; returns (session id, turn text).

    Chat streams open with a session event; run streams don't carry one. In
    collect mode nothing is printed to stdout — deltas accumulate, status and
    tool lines are dropped, and errors still reach stderr."""
    session_id: str | None = None
    text_parts: list[str] = []
    for event in events:
        kind = event.get("type")
        if kind == "session":
            session_id = event["session_id"]
        elif kind == "status":
            if not collect:
                console.print(f"[dim]{event.get('stage', 'working')}…[/dim]")
        elif kind == "text":
            delta = event.get("delta", "")
            text_parts.append(delta)
            if not collect:
                print(delta, end="", flush=True)
        elif kind == "tool":
            if not collect:
                console.print(f"\n[dim]{_render_tool_event(event)}[/dim]")
        elif kind == "error":
            if collect:
                echo_error(f"Error: {event.get('message')}")
            else:
                console.print(f"\n[red]Error: {event.get('message')}[/red]")
        elif kind == "end":
            if not collect:
                print()
    return session_id, "".join(text_parts)


@agent_app.command("list")
def agent_list(as_json: bool = typer.Option(False, "--json")):
    """List your configured agents (personas, models, schedules)."""
    with _client() as c:
        try:
            agents = c.list_agents()
        except StashError as e:
            _err(e)
    if not agents:
        print_empty_state("agents")
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
    session: str = typer.Option(
        None, "--session", "-s", help="Continue an existing chat session (id or title)."
    ),
    agent: str = typer.Option(
        None, "--agent", "-a", help="Agent name or id. Default agent if omitted."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Start (or continue) a cloud agent chat and stream the turn live.

    Ctrl-C disconnects the stream, which stops the turn on the box."""
    use_json = _use_json(as_json)
    session = _resolve_session(session) if session else None
    with _client() as c:
        try:
            agent_id = _resolve_agent_id(c, agent) if agent else None
            session_id, text = _stream_turn(
                c.agent_chat_events(message, session_id=session, agent_id=agent_id),
                collect=use_json,
            )
        except StashError as e:
            _err(e)
    if use_json:
        output_json({"session_id": session_id, "text": text})
        return
    if session_id:
        console.print(
            f"[dim]session {session_id} — continue with "
            f'[bold]stash agent chat -s {session_id} "…"[/bold][/dim]'
        )


@agent_app.command("run")
def agent_run(
    agent: str = typer.Argument(..., help="Scheduled agent name or id."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Run a prompt-scheduled agent now and stream the run live."""
    use_json = _use_json(as_json)
    with _client() as c:
        try:
            agent_id = _resolve_agent_id(c, agent)
            session_id, text = _stream_turn(c.agent_run_events(agent_id), collect=use_json)
        except StashError as e:
            _err(e)
    if use_json:
        output_json({"session_id": session_id, "text": text})


@agent_app.command("status")
def agent_status(
    session_id: str = typer.Argument(..., help="The chat session (id or title) to check."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Whether a turn is currently running in a chat session."""
    session_id = _resolve_session(session_id)
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
    session_id: str = typer.Argument(..., help="The chat session (id or title) to follow."),
    poll_seconds: float = typer.Option(2.0, "--poll", help="Poll interval in seconds."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Follow a chat session live — works for turns started anywhere
    (web, Slack, a schedule, or another terminal). Exits when the turn ends."""
    use_json = _use_json(as_json)
    session_id = _resolve_session(session_id)
    role_style = {"user": "[bold]you:[/bold] ", "assistant": "", "tool": "[dim]", "": ""}
    with _client() as c:
        seen = 0
        messages: list[dict] = []
        while True:
            try:
                # Status before messages: a turn that ends between the two
                # calls still gets its final message printed this pass.
                status = c.agent_turn_status(session_id)
                messages = c.get_agent_chat(session_id)["messages"]
            except StashError as e:
                _err(e)
            if not use_json:
                for m in messages[seen:]:
                    prefix = role_style.get(m["role"], "")
                    suffix = "[/dim]" if m["role"] == "tool" else ""
                    console.print(f"{prefix}{m['content']}{suffix}\n")
            seen = len(messages)
            if not status["running"]:
                break
            time.sleep(poll_seconds)
    if use_json:
        output_json({"session_id": session_id, "messages": messages})
        return
    console.print("[dim]Turn finished — chat is idle.[/dim]")


@agent_app.command("stop")
def agent_stop(
    session_id: str = typer.Argument(
        ..., help="The chat session (id or title) whose turn to stop."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Stop the turn running in a chat session (kills the run on the box)."""
    session_id = _resolve_session(session_id)
    with _client() as c:
        try:
            c.stop_agent_turn(session_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "session_id": session_id})
        return
    console.print("⏹ Stop requested — the turn will end shortly.")


# ===========================================================================
# Sources — unified VFS over native files/sessions + connected sources
# ===========================================================================

sources_app = typer.Typer(
    help="Sources — connect, sync, and disconnect external sources. "
    "Browse and read their contents with `stash vfs` under /sources."
)
app.add_typer(sources_app, name="sources")


def _print_search(
    query: str,
    source: str,
    include_sources: str,
    exclude_sources: str,
    limit: int,
    as_json: bool,
    modified_after: str = "",
    modified_before: str = "",
) -> None:
    """Shared body for `stash search`."""
    telemetry.record("sources.search")
    with _client() as c:
        try:
            data = c.search_sources(
                query,
                source=source or None,
                include_sources=split_source_tokens(include_sources),
                exclude_sources=split_source_tokens(exclude_sources),
                limit=limit,
                modified_after=modified_after or None,
                modified_before=modified_before or None,
            )
        except StashError as e:
            _err(e)
    hits = data["results"]
    if not hits:
        print_empty_state("matches")
    if _use_json(as_json):
        output_json(data)
        return
    for hit in hits:
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
        # The server sends a ~300-char window centered on the first query
        # match, edges already marked with "…" — printable as-is.
        snippet = (hit.get("snippet") or "").replace("\n", " ").strip()
        if snippet:
            console.print(f"    {snippet}")
    if data["has_more"]:
        console.print("  [dim]More matches exist — raise -n or refine the query.[/dim]")


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Search query."),
    source: str = typer.Option(
        "", "--source", help="Scope to one source handle (omit to search everything)."
    ),
    include_sources: str = typer.Option(
        "",
        "--include-sources",
        help="Comma-separated sources to search (files, sessions, gmail, jira, …). "
        "Not combinable with --source.",
    ),
    exclude_sources: str = typer.Option(
        "",
        "--exclude-sources",
        help="Comma-separated sources to skip. Not combinable with --source.",
    ),
    modified_after: str = typer.Option(
        "",
        "--modified-after",
        help="Only results last modified after this ISO timestamp (e.g. 2026-01-01). "
        "Results with no known modification time are excluded.",
    ),
    modified_before: str = typer.Option(
        "",
        "--modified-before",
        help="Only results last modified before this ISO timestamp. "
        "Results with no known modification time are excluded.",
    ),
    limit: int = typer.Option(20, "-n", "--limit"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Search everything you can see — files, sessions, and connected sources."""
    _print_search(
        query,
        source,
        include_sources,
        exclude_sources,
        limit,
        as_json,
        modified_after=modified_after,
        modified_before=modified_before,
    )


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


memory_app = typer.Typer(
    help="Your Memory wiki — status, recompute, and direct page writes.",
    invoke_without_command=True,
)
app.add_typer(memory_app, name="memory")


@memory_app.callback()
def memory_default(
    ctx: typer.Context,
    recompute: bool = typer.Option(
        False,
        "--recompute",
        help="Run the Memory curator now instead of waiting for the daily pass.",
    ),
    curator: str = typer.Option(
        None,
        "--curator",
        help="Turn the curator's nightly cloud run 'on' or 'off'. Turn it off when "
        "you curate locally; --recompute still works while it's off.",
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show your reserved Memory folder (its id is where the wiki lives)."""
    if ctx.invoked_subcommand is not None:
        return
    if curator is not None and curator not in ("on", "off"):
        console.print("[red]--curator takes 'on' or 'off'.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        if curator is not None:
            row = c.get_curator()
            if not row:
                console.print("[red]No Memory curator found for this account.[/red]")
                raise typer.Exit(1)
            updated = c.set_curator_scheduled(row["id"], curator == "on")
            if _use_json(as_json):
                output_json(updated)
            elif curator == "on":
                console.print(
                    "Curator nightly cloud run: [green]on[/green] — resumes at the next daily tick."
                )
            else:
                console.print(
                    "Curator nightly cloud run: [yellow]off[/yellow] — "
                    "run it yourself with `stash memory --recompute` or locally."
                )
            return
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
        row = c.get_curator()
    if _use_json(as_json):
        output_json({**folder, "curator": row})
        return
    console.print(f"Memory folder: [cyan]{folder['name']}[/cyan] (id {folder['id']})")
    if row:
        schedule = "nightly (cloud)" if row["run_mode"] == "scheduled" else "off — on-demand only"
        console.print(f"Curator schedule: {schedule}")
        last_run = row["last_run_at"] or "never"
        console.print(f"Curator last run: {last_run}")
        if row["last_run_error"]:
            console.print(f"[red]Curator last run failed:[/red] {row['last_run_error']}")


def _resolve_memory_target(c: StashClient, path: str) -> tuple[dict | None, str, str]:
    """Walk `path` (relative to the Memory folder) to its page slot.

    Returns (existing_page | None, folder_id, page_name), creating missing
    intermediate folders along the way. A trailing `.md` on the page segment
    is stripped — the VFS shows page names with that suffix."""
    segments = [s for s in path.split("/") if s]
    page_name = segments[-1].removesuffix(".md") if segments else ""
    if not page_name:
        raise ValueError(f"not a page path: {path!r}")
    folder_id = c.get_memory_folder()["id"]
    node: dict | None = c.get_memory_tree()
    for segment in segments[:-1]:
        child = next((f for f in node["folders"] if f["name"] == segment), None) if node else None
        if child is None:
            folder_id = c.create_folder(segment, parent_folder_id=folder_id)["id"]
            node = None
        else:
            folder_id = child["id"]
            node = child
    pages = node["pages"] if node else []
    page = next((p for p in pages if p["name"] == page_name), None)
    return page, folder_id, page_name


@memory_app.command("write")
def memory_write(
    path: str = typer.Argument(
        ...,
        help="Page path under the Memory folder, e.g. 'Product/Chainbase'. "
        "Missing subfolders are created; a trailing .md is stripped.",
    ),
    content: str = typer.Option(None, "--content", help="Page body. Reads stdin if omitted."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create or update a Memory wiki page at a path — the direct write
    surface for agents that maintain the wiki themselves."""
    if content is None and not sys.stdin.isatty():
        content = sys.stdin.read()
    if content is None:
        console.print("[red]No content: pass --content or pipe the body on stdin.[/red]")
        raise typer.Exit(1)
    with _client() as c:
        try:
            page, folder_id, page_name = _resolve_memory_target(c, path)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        except StashError as e:
            _err(e)
        try:
            if page is None:
                data = c.create_page(page_name, content=content, folder_id=folder_id)
                action = "created"
            else:
                data = c.update_page(page["id"], content=content)
                action = "updated"
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({**data, "action": action})
    else:
        console.print(f"[green]Page '{data['name']}' {action}.[/green]  ID: {data['id']}")


def _print_memory_tree(node: dict, indent: int) -> None:
    pad = "  " * indent
    for f in node["folders"]:
        console.print(f"{pad}[cyan]{f['name']}/[/cyan]  [dim]{f['id']}[/dim]")
        _print_memory_tree(f, indent + 1)
    for p in node["pages"]:
        console.print(f"{pad}{p['name']}  [dim]{p['id']}[/dim]")


@memory_app.command("ls")
def memory_ls(as_json: bool = typer.Option(False, "--json")):
    """The Memory wiki tree with ids — page ids feed `stash files edit-page`
    and `stash rm page:<id>`."""
    with _client() as c:
        try:
            folder = c.get_memory_folder()
            tree = c.get_memory_tree()
        except StashError as e:
            _err(e)
    if not tree.get("folders") and not tree.get("pages"):
        print_empty_state("pages or folders")
    if _use_json(as_json):
        output_json({"id": folder["id"], "name": folder["name"], **tree})
        return
    console.print(f"[cyan]{folder['name']}/[/cyan]  [dim]{folder['id']}[/dim]")
    _print_memory_tree(tree, indent=1)


@app.command("changes")
def changes(
    since: str = typer.Option(None, "--since", help="ISO timestamp; omit for everything."),
    as_json: bool = typer.Option(False, "--json"),
):
    """What changed since a timestamp — history, pages, files, saves, sources.
    Feeds the Memory curator's incremental pass."""
    with _client() as c:
        data = c.get_changes(since or None)
    if _use_json(as_json):
        output_json(data)
        return
    counts = data.get("counts", {})
    console.print(
        f"Changes since {data.get('since') or 'the beginning'}: "
        f"{counts.get('history', 0)} events, {counts.get('pages', 0)} pages, "
        f"{counts.get('files', 0)} files, {counts.get('saves', 0)} saves, "
        f"{counts.get('sources', 0)} sources"
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
def sources_rm(source_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Disconnect a source you own (its indexed documents cascade away)."""
    with _client() as c:
        try:
            c.delete_source(source_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "source_id": source_id})
        return
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
    if not sources:
        print_empty_state("sources")
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
        _exit_user_error(f"No source named '{dir_name}'. Run `stash ls` to see them.")

    if source["type"] == "provider":
        _print_provider_path(c, source, rest, as_json)
        return

    entries = c.list_source_entries(source["source"], path=rest)
    if not entries:
        print_empty_state("files or folders")
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
            _exit_user_error(f"No connection '{member_slug}' under '{provider['source']}'.")
        handle = member["handle"]

    entries = c.list_source_entries(handle, path=doc_path)
    if not entries:
        print_empty_state("files or folders")
    if _use_json(as_json):
        output_json({"entries": entries})
        return
    if entries:
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
        print_empty_state("files or folders")
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
            _exit_user_error(f"Invalid item '{ref}' — use type:id, e.g. page:<id>")
        object_type, object_id = ref.split(":", 1)
        parsed.append((object_type, object_id))
    return parsed


def _resolve_session_refs(
    items: list[tuple[str, str]], *, trashed: bool = False
) -> list[tuple[str, str]]:
    """Session refs may carry a title instead of an id — resolve each to the
    session row id the rm/restore/mv endpoints take.

    `trashed` picks which listing the title is matched against: `restore`
    names sessions the overview has already dropped."""
    resolved = []
    for object_type, ref in items:
        if object_type != "session":
            resolved.append((object_type, ref))
        elif trashed:
            resolved.append((object_type, _resolve_trashed_session(ref)))
        else:
            resolved.append((object_type, _resolve_session(ref, field="id")))
    return resolved


@app.command("rm")
def rm_cmd(
    refs: list[str] = typer.Argument(
        ...,
        help="Items as type:id (session refs also accept a title). Types: page | file | session",
    ),
    permanent: bool = typer.Option(
        False, "--permanent", help="Skip the trash window — delete immediately."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Move pages, files, or sessions to trash. Pass --permanent to wipe immediately.

    Idempotent: an item already in trash (or already gone) is a no-op — the
    command exits 0 and reports it instead of erroring on the 404.

    Example: stash rm page:<id> file:<id> session:<id>
    """
    trash = {
        "page": (lambda c, i: c.delete_page(i), lambda c, i: c.purge_page(i)),
        "file": (lambda c, i: c.delete_file(i), lambda c, i: c.purge_file(i)),
        "session": (lambda c, i: c.delete_session(i), lambda c, i: c.purge_session(i)),
    }
    items = _resolve_session_refs(_parse_refs(refs))
    use_json = _use_json(as_json)
    changed = 0
    noops = 0
    with _client() as c:
        for object_type, object_id in items:
            if object_type not in trash:
                _exit_user_error(f"Cannot rm '{object_type}'. Supported: page | file | session")
            delete, purge = trash[object_type]
            try:
                delete(c, object_id)
                if permanent:
                    purge(c, object_id)
                changed += 1
            except StashError as e:
                # A 404 means the item is already in the end state rm wants
                # (in trash or permanently gone): re-running is an idempotent
                # no-op, not an error. Any other status is a real failure.
                if e.status_code != 404:
                    _err(e)
                noops += 1
    verb = "permanently deleted" if permanent else "moved to trash"
    state = "already permanently deleted" if permanent else "already in trash"
    if changed and noops:
        echo_stderr(f"  {noops} item(s) {state} — skipped.")
    if changed:
        _report_mutation(
            use_json,
            True,
            f"{len(items)} item(s) {verb}.",
            markup=f"[green]{len(items)} item(s) {verb}.[/green]",
        )
        return
    _report_mutation(use_json, False, f"All {len(items)} item(s) {state} — nothing to do.")


@app.command("restore")
def restore_cmd(
    refs: list[str] = typer.Argument(
        ...,
        help="Items as type:id (session refs also accept a title). Types: page | file | session",
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Restore pages, files, or sessions from trash.

    A session may be named by its title, as `stash trash list` prints it:
    stash restore page:<id> session:"<title>"

    Idempotent: an item already restored is a no-op — the command exits 0 and
    reports it instead of erroring on the 404.
    """
    restore = {
        "page": lambda c, i: c.restore_page(i),
        "file": lambda c, i: c.restore_file(i),
        "session": lambda c, i: c.restore_session(i),
    }
    items = _resolve_session_refs(_parse_refs(refs), trashed=True)
    use_json = _use_json(as_json)
    changed = 0
    noops = 0
    with _client() as c:
        for object_type, object_id in items:
            if object_type not in restore:
                _exit_user_error(
                    f"Cannot restore '{object_type}'. Supported: page | file | session"
                )
            try:
                restore[object_type](c, object_id)
                changed += 1
            except StashError as e:
                # A 404 means the item is no longer in trash — it is already
                # restored: re-running is an idempotent no-op, not an error.
                if e.status_code != 404:
                    _err(e)
                noops += 1
    if changed and noops:
        echo_stderr(f"  {noops} item(s) already restored — skipped.")
    if changed:
        _report_mutation(
            use_json,
            True,
            f"{len(items)} item(s) restored.",
            markup=f"[green]{len(items)} item(s) restored.[/green]",
        )
        return
    _report_mutation(use_json, False, f"All {len(items)} item(s) already restored — nothing to do.")


@app.command("mv")
def mv_cmd(
    refs: list[str] = typer.Argument(
        ...,
        help=f"Items as type:id (session refs also accept a title). Types: {_OBJECT_TYPES}",
    ),
    to_folder: str = typer.Option(None, "--to-folder", help="Target folder id."),
    to_root: bool = typer.Option(False, "--to-root", help="Move to the root."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Move objects into a folder (or to the root with --to-root).

    Example: stash mv page:<id> file:<id> --to-folder <id>
    """
    if not to_folder and not to_root:
        _exit_user_error("Pass --to-folder <id> or --to-root.")
    # Sessions can't be moved — session folders were removed with the
    # developer platform work; sessions live in the flat sessions surface.
    items = _parse_refs(refs)
    moves = [{"object_type": t, "object_id": i} for t, i in items]
    with _client() as c:
        try:
            c.batch_move(moves, target_folder_id=to_folder, move_to_root=to_root)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "items": len(items)})
        return
    console.print(f"[green]{len(items)} item(s) moved.[/green]")


@app.command("cp")
def cp_cmd(
    refs: list[str] = typer.Argument(..., help="Items as type:id. Types: page | file | folder"),
    to_folder: str = typer.Option(None, "--to-folder", help="Target folder id."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Duplicate pages, files, or folders as 'Copy of <name>'.

    Example: stash cp page:<id> folder:<id> --to-folder <id>
    """
    copy = {
        "page": lambda c, i: c.copy_page(i, target_folder_id=to_folder or None),
        "file": lambda c, i: c.copy_file(i, target_folder_id=to_folder or None),
        "folder": lambda c, i: c.copy_folder(i, target_folder_id=to_folder or None),
    }
    copies = []
    for object_type, object_id in _parse_refs(refs):
        if object_type not in copy:
            _exit_user_error(f"Cannot cp '{object_type}'. Supported: page | file | folder")
        with _client() as c:
            try:
                made = copy[object_type](c, object_id)
            except StashError as e:
                _err(e)
        copies.append({"id": made["id"], "name": made["name"]})
    if _use_json(as_json):
        output_json({"ok": True, "copies": copies})
        return
    for made in copies:
        console.print(f"[green]Copied to[/green] {made['name']} ({made['id']})")


# ===========================================================================
# Shares — grant a person access to a folder/page/file/session by email
# ===========================================================================

shares_app = typer.Typer(help="Shares — grant people access to an object by email.")
app.add_typer(shares_app, name="shares")

_SHARE_OBJECT_TYPES = "folder | page | file | session | table | source"


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
    if not data:
        print_empty_state("shares")
    if _use_json(as_json):
        output_json(data)
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
    if object_type == "session":
        object_id = _resolve_session(object_id, field="id")
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Revoke a person's access to an object."""
    if object_type == "session":
        object_id = _resolve_session(object_id, field="id")
    with _client() as c:
        try:
            c.unshare_object(object_type, object_id, principal_type, principal_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "object_id": object_id})
        return
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
    all_empty = all(not data.get(kind) for kind in ("pages", "files", "sessions"))
    if all_empty:
        print_empty_state("trash")
    if _use_json(as_json):
        output_json(data)
        return
    if all_empty:
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Delete a row from a table."""
    with _client() as c:
        try:
            c.delete_table_row(table_id, row_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "row_id": row_id})
        return
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
    as_json: bool = typer.Option(False, "--json"),
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
    if _use_json(as_json):
        output_json({"table_id": table_id, "csv": csv_content})
        return
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
    as_json: bool = typer.Option(False, "--json"),
):
    """Delete a table and all its data."""
    if not yes and not _use_json(as_json):
        typer.confirm("Delete this table and all its data?", abort=True)
    with _client() as c:
        try:
            c.delete_table(table_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "table_id": table_id})
        return
    console.print("[green]Table deleted.[/green]")


# ===========================================================================
# Uploaded files
# ===========================================================================


def _upload_path(c: StashClient, path: str) -> dict:
    """Upload `path` to your Files. Returns FileResponse dict."""
    if not Path(path).is_file():
        console.print(f"[red]Not a file: {path}[/red]")
        raise typer.Exit(1)
    if Path(path).suffix.lower() in _HTML_UPLOAD_EXTENSIONS:
        return _upload_html_with_assets(c, Path(path))
    return c.upload_file(path)


# src="chart.png" / href="logo.svg" / poster="…" / url(bg.png) — the forms an
# exported HTML file uses to point at a picture sitting next to it.
_HTML_ASSET_REF = re.compile(
    r"""(?P<prefix>(?:src|href|poster)\s*=\s*["']|url\(\s*["']?)(?P<url>[^"')]+)""",
    re.IGNORECASE,
)
_HTML_ASSET_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".avif",
    ".bmp",
    ".ico",
    ".mp4",
    ".webm",
    ".ogg",
    ".mp3",
    ".wav",
}


def _upload_html_with_assets(
    c: StashClient,
    html_path: Path,
    folder_id: str | None = None,
    known_assets: dict[Path, str] | None = None,
) -> dict:
    """Upload an HTML file along with the pictures it points at.

    An exported report references its images by relative path. Uploading only
    the markup leaves every one of them pointing at a path that doesn't exist
    on the server, so the page renders with broken images. Each referenced file
    that exists on disk is uploaded and its reference rewritten to the file's
    permanent download route — the one route that also serves viewers holding a
    public link. Anything already uploaded by the caller (`known_assets`) is
    reused rather than uploaded twice.
    """
    html = html_path.read_text(errors="replace")
    uploaded: dict[Path, str] = dict(known_assets or {})
    rewritten: dict[str, str] = {}
    # Assets uploaded here sit at the root with no parent folder, so they
    # inherit no visibility. A public page whose pictures stay private renders
    # with broken images, so the caller has to grant them too.
    asset_file_ids: list[str] = []

    for match in _HTML_ASSET_REF.finditer(html):
        ref = match.group("url").strip()
        if ref in rewritten or not ref:
            continue
        # Absolute URLs, data: payloads, and in-page anchors are already fine.
        if ref.startswith(("http://", "https://", "//", "data:", "#", "mailto:", "/")):
            continue
        asset = (html_path.parent / ref.split("?")[0].split("#")[0]).resolve()
        if asset.suffix.lower() not in _HTML_ASSET_EXTENSIONS or not asset.is_file():
            continue
        if asset not in uploaded:
            asset_id = c.upload_file(str(asset))["id"]
            uploaded[asset] = f"/api/v1/me/files/{asset_id}/download"
            asset_file_ids.append(asset_id)
            console.print(f"  [dim]Asset: {asset.name}[/dim]")
        rewritten[ref] = uploaded[asset]

    if rewritten:
        for ref, url in rewritten.items():
            html = html.replace(ref, url)
        # The server names the page from the filename, so the rewritten copy
        # has to keep it.
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / html_path.name
            staged.write_text(html)
            page = c.upload_file(str(staged), folder_id)
    else:
        page = c.upload_file(str(html_path), folder_id)
    page["asset_file_ids"] = asset_file_ids
    return page


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
def files_text(file_id: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
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
        if _use_json(as_json):
            output_json({"text": text, "file_id": file_id})
            return
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    if status in ("pending", "processing"):
        echo_stderr("Extraction in progress. Try again in a moment.")
        raise typer.Exit(EXIT_INTERNAL_ERROR)
    if status == "failed":
        _exit_internal_error(f"Extraction failed: {error or 'unknown error'}")
    if _use_json(as_json):
        output_json({"text": None, "file_id": file_id})
        return
    echo_stderr("No extracted text available for this file.")
    raise typer.Exit(EXIT_SUCCESS)


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
    as_json: bool = typer.Option(False, "--json"),
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
    if _use_json(as_json):
        output_json({"ok": True, "bytes": len(data), "name": meta["name"]})
        return
    console.print(f"[green]Downloaded[/green] {meta['name']} → {dest} [dim]{len(data)} bytes[/dim]")


# ===========================================================================
# Connect wizard
# ===========================================================================


def _reserve_bottom_padding(lines: int = 4) -> None:
    """Scroll the terminal up `lines` rows so prompts don't render flush against the bottom."""
    sys.stdout.write("\n" * lines + f"\033[{lines}A")
    sys.stdout.flush()


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


def _auto_connect_repo(repo_root: Path, cfg: dict, use_json: bool = False) -> None:
    """Write `.stash` and append Stash context to CLAUDE.md in `repo_root`.

    Works in any folder — a git repo is not required. Does not touch the
    global streaming toggle; callers decide that. In JSON mode the status
    lines go to stderr; stdout carries only the result document."""
    if use_json:

        def status(markup: str, plain: str) -> None:
            echo_stderr(plain)
    else:

        def status(markup: str, plain: str) -> None:
            console.print(markup)

    manifest_path = repo_root / MANIFEST_FILE

    if manifest_path.is_file():
        status("  [green]✓[/green] Already connected.", "  ✓ Already connected.")
        return

    base_url = cfg.get("base_url", PRODUCTION_BASE_URL)

    manifest: Manifest = {}
    if base_url != PRODUCTION_BASE_URL:
        manifest["base_url"] = base_url

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    status(f"  Wrote [cyan]{MANIFEST_FILE}[/cyan]", f"  Wrote {MANIFEST_FILE}")

    _append_claude_md(repo_root, use_json=use_json)

    if _git_toplevel(repo_root):
        status(
            f"\n  Commit [cyan]{MANIFEST_FILE}[/cyan] and [cyan]CLAUDE.md[/cyan] and push. "
            "Teammates will start streaming automatically.",
            "\n  Commit .stash and CLAUDE.md and push. "
            "Teammates will start streaming automatically.",
        )


def _append_claude_md(repo_root: Path, use_json: bool = False) -> None:
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
- Share a coding session → `stash share` (this one), or `stash share --session "<title>"` for another.

Run `stash prompts agent-guidance` to reprint this rule mid-session.

### Browsing Stash

Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS:
- `stash vfs ls /`
- `stash vfs "find / -maxdepth 3 -type f"`
- `stash vfs "rg 'query' /"`
- `stash vfs "cat '/files/README.md'"`

Common reads:
- `stash search "<query>" --json` — full-text search across files, sessions, and connected sources
- `stash vfs "ls /"` — browse your files, sessions, tables, skills, and connected sources
- `stash sql "SELECT ..."` — query your tables with SQL (tables live in the folder tree; bare name when unique, '"files/<folder>".<name>' otherwise)
- `stash vfs "cat '/sessions/_index.jsonl'"` — recent sessions
- `stash sessions agents` — who's been active

Common writes:
- `stash memory write "<Topic>/<Page>" --content "..."` — fold what you learned into the Memory wiki
- `stash share --title "..."` — share this session as a public Skill
- `stash read <url>` — read a public Skill URL
"""
    claude_md.write_text(existing.rstrip() + "\n" + block)
    if use_json:
        echo_stderr("  Appended Stash context to CLAUDE.md")
    else:
        console.print("  Appended Stash context to [cyan]CLAUDE.md[/cyan]")


_AGENT_LABEL = {
    "claude": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex",
    "opencode": "opencode",
    "gemini": "Gemini CLI",
    "openclaw": "Openclaw",
    "hermes": "Hermes",
    "pi": "Pi",
}


def _pick_agents(message: str, agents: list[str], checked: list[str]) -> list[str] | None:
    """Agent multi-select where enter (or space) toggles the highlighted agent
    and a Done row submits — enter never means "save" while pointing at an
    agent. Custom prompt_toolkit widget because questionary's checkbox
    hard-binds enter to submit. Returns None if dismissed with Ctrl-C."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    selected = set(checked)
    row = 0
    done_row = len(agents)

    def fragments():
        lines = [
            ("class:qmark", "? "),
            ("class:question", message),
            ("class:instruction", "  (enter toggles an agent, Done saves)\n"),
            (
                "class:instruction",
                "   [x] = uploads its sessions to your Stash. Unchecked agents upload "
                "nothing\n   but can still use the stash CLI — anyone can use a CLI.\n",
            ),
        ]
        for i, agent in enumerate(agents):
            box = "[x]" if agent in selected else "[ ]"
            label = _AGENT_LABEL.get(agent, agent)
            lines.append(("class:pointer", " » " if row == i else "   "))
            lines.append(("class:checked" if agent in selected else "", f"{box} {label}\n"))
        lines.append(("class:pointer", " » " if row == done_row else "   "))
        lines.append(("bold", "Done"))
        return lines

    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        nonlocal row
        row = (row - 1) % (done_row + 1)

    @kb.add("down")
    def _down(event):
        nonlocal row
        row = (row + 1) % (done_row + 1)

    @kb.add("enter")
    @kb.add(" ")
    def _toggle_or_submit(event):
        if row == done_row:
            event.app.exit(result=[a for a in agents if a in selected])
            return
        agent = agents[row]
        if agent in selected:
            selected.remove(agent)
        else:
            selected.add(agent)

    @kb.add("c-c")
    def _abort(event):
        event.app.exit(result=None)

    picker = Application(
        layout=Layout(Window(FormattedTextControl(fragments), height=len(agents) + 4)),
        key_bindings=kb,
        erase_when_done=True,
        style=Style(
            [
                ("qmark", "fg:#5f819d"),
                ("question", "bold"),
                ("instruction", "fg:#858585"),
                ("checked", "fg:#16a34a"),
            ]
        ),
    )
    result = picker.run()
    if result is not None:
        labels = ", ".join(_AGENT_LABEL.get(a, a) for a in result) or "none"
        console.print(f"[bold]?[/bold] {message}  [#FF9D00]{labels}[/#FF9D00]")
    return result


def _install_all_hooks(agents: list[str] | None = None, use_json: bool = False) -> None:
    """Install/upgrade hooks for the given agents (defaults to all detected).

    In JSON mode the per-agent ✓/✗ lines and the Codex trust notice go to
    stderr; stdout stays reserved for the caller's single JSON document."""
    detected = _detected_agents()
    if not detected:
        return

    to_install = [a for a in detected if a in agents] if agents is not None else detected

    def status(markup: str, plain: str) -> None:
        if use_json:
            echo_stderr(plain)
        else:
            console.print(markup)

    codex_needs_trust = False
    for agent in to_install:
        try:
            status_, detail = _INSTALLERS[agent](False, use_json)
        except Exception as e:
            status_, detail = ("failed", f"{type(e).__name__}: {e}")
        if status_ == "installed":
            status(
                f"  [green]✓[/green] {_AGENT_LABEL[agent]} hook installed  {detail}",
                f"  ✓ {_AGENT_LABEL[agent]} hook installed  {detail}",
            )
        elif status_ == "skipped":
            status(
                f"  [green]✓[/green] {_AGENT_LABEL[agent]} hook up to date",
                f"  ✓ {_AGENT_LABEL[agent]} hook up to date",
            )
        elif status_ == "failed":
            status(
                f"  [red]✗[/red] {_AGENT_LABEL[agent]} hook failed  {detail}",
                f"  ✗ {_AGENT_LABEL[agent]} hook failed  {detail}",
            )
        if agent == "codex" and status_ == "installed":
            codex_needs_trust = True

    # Codex only runs new or changed command hooks after the user approves
    # them, so streaming is not live until that happens.
    if codex_needs_trust:
        status(
            "\n  [yellow]Codex hooks were installed or changed — Codex will not run them"
            " until you trust them:[/yellow]\n"
            "    1. Restart Codex.\n"
            "    2. When Codex prompts to review new hooks (or via its /hooks review),"
            " approve the Stash hooks.\n"
            "  Codex sessions start streaming to Stash only after the hooks are trusted.",
            "\n  Codex hooks were installed or changed — Codex will not run them"
            " until you trust them:\n"
            "    1. Restart Codex.\n"
            "    2. When Codex prompts to review new hooks (or via its /hooks review),"
            " approve the Stash hooks.\n"
            "  Codex sessions start streaming to Stash only after the hooks are trusted.",
        )


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
    as_json: bool = typer.Option(
        False, "--json", help="Emit a result object on stdout instead of human text."
    ),
):
    """Sign in to Stash through the browser.

    Run interactively for guided first-run setup (session recording, agent
    hooks, folder context) — re-runnable later via `stash setup`. With
    --non-interactive — or whenever stdin isn't a terminal — it skips the
    wizard and just authenticates, which is the path installers and agents use. The browser opens automatically when one is available, and
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
            _exit_user_error("Pass --api <url> with --api-key — the server that minted the key.")
        try:
            with StashClient(base_url=api, api_key=api_key) as c:
                user = c.whoami()
        except StashError as e:
            _exit_user_error(f"Could not authenticate against {api}: {e.detail}")
        save_config(base_url=api, api_key=api_key, username=user["name"])
        if _use_json(as_json):
            output_json({"ok": True, "username": user["name"], "api": api})
            return
        console.print(f"[green]Authenticated as {user['name']}[/green]")
        return

    # Scripted / headless: bare browser auth, no wizard prompts.
    # The interactive wizard below only runs on a real TTY; JSON mode is the
    # agent path, which is always headless, so only these scripted branches
    # emit JSON.
    if non_interactive or not sys.stdin.isatty():
        base_url = api or stored_base_url() or PRODUCTION_BASE_URL
        api_key, username = _browser_auth_flow(base_url, timeout=timeout)
        save_config(base_url=base_url, api_key=api_key, username=username)
        if _use_json(as_json):
            output_json({"ok": True, "username": username, "api": base_url})
            return
        console.print(f"[green]✓ Signed in as {username}[/green]")
        return

    console.print("\n[bold]Stash sign-in[/bold]\n")

    cfg = load_config()

    # --- Step 1: API endpoint ---
    # Managed by default; self-hosters point at their instance with --api.
    base_url = api or stored_base_url() or PRODUCTION_BASE_URL
    save_config(base_url=base_url)
    if base_url == PRODUCTION_BASE_URL:
        console.print(
            "  [dim]Self-hosting? Re-run with[/dim] stash signin --api <your-instance-url>"
        )
    else:
        console.print(f"  [green]✓[/green] Using endpoint: [bold]{base_url}[/bold]")

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
        console.print(
            "\n  Run [cyan]stash setup[/cyan] to redo setup, or "
            "[cyan]stash settings[/cyan] to change agents or endpoint."
        )
        return

    _run_setup_wizard()


def _agent_folder_candidates(limit: int = 6) -> list[tuple[Path, int]]:
    """Folders the user actually runs agents in, ranked by session count —
    mined from the same transcript history the importer reads, so the folder
    question can offer real answers instead of a blank path prompt. Only
    folders that still exist qualify."""
    from .import_history import discover_conversations

    counts: dict[str, int] = {}
    for conv in discover_conversations():
        # Cursor reports an encoded project slug rather than a path
        # (import_history._encode_cursor_dir), and a relative entry in
        # recorded_paths resolves against each session's own cwd — matching
        # nothing, which the scope gate reads as "record nothing at all".
        if conv.cwd and conv.cwd.startswith("/"):
            counts[conv.cwd] = counts.get(conv.cwd, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    result: list[tuple[Path, int]] = []
    for raw, count in ranked:
        path = Path(raw)
        if path.is_dir():
            result.append((path, count))
        if len(result) == limit:
            break
    return result


def _pretty_path(path: Path) -> str:
    home = Path.home()
    raw = str(path)
    if path != home and home not in path.parents:
        return raw
    return "~" + raw[len(str(home)) :]


# AppleScript's "User canceled." Matched as the trailing error code, never as a
# substring of the message: osascript echoes the offending path into stderr, so
# a plain `"-128" in stderr` reads a real failure under ~/work/PROJ-128 as a
# cancel and drops the user's answer on the floor.
_APPLESCRIPT_CANCELED = re.compile(r"\(-128\)\s*$")


def _choose_folder_finder(start: Path) -> Path | None:
    """Pop the native macOS Finder folder chooser. None means the user hit
    Cancel; any other failure (e.g. an SSH session with no GUI) raises so the
    user re-runs and picks "Type a path" instead of silently losing the answer."""
    import subprocess

    # A quoted AppleScript string: backslashes first, then the quotes that end it.
    literal = str(start).replace("\\", "\\\\").replace('"', '\\"')
    script = (
        "POSIX path of (choose folder with prompt "
        '"Where should Stash record agent sessions?" '
        f'default location POSIX file "{literal}")'
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    stderr = result.stderr.strip()
    if result.returncode != 0:
        if _APPLESCRIPT_CANCELED.search(stderr):
            return None
        raise RuntimeError(f"Finder dialog failed: {stderr}")
    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError("Finder dialog returned no folder")
    return Path(raw)


def _browse_folders(start: Path) -> Path | None:
    """Arrow-key folder browser: 'record this folder' pinned on top, '..' to
    go up, subfolders to drill into. No typing required."""
    cur = start.resolve()
    while True:
        # An unreadable directory is not an empty one: rendering it as empty
        # would let the user record a folder believing they saw its contents.
        subdirs = sorted(
            (d for d in cur.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=lambda d: d.name.lower(),
        )
        use = f"✓ Record {_pretty_path(cur)}"
        up = ".. (up one level)"
        choices: list[str] = [use]
        if cur.parent != cur:
            choices.append(up)
        choices.extend(f"{d.name}/" for d in subdirs)
        _reserve_bottom_padding(min(len(choices), 15) + 2)
        picked = questionary.select(f"Browsing {_pretty_path(cur)}", choices=choices).ask()
        if picked is None:
            return None
        if picked == use:
            return cur
        if picked == up:
            cur = cur.parent
            continue
        cur = cur / picked.rstrip("/")


def _pick_record_folder(start: Path) -> Path | None:
    """The ergonomic folder choice: your agents' actual working folders first,
    a browser second, a typed path as the escape hatch."""
    candidates = _agent_folder_candidates()
    native = sys.platform == "darwin"
    browse = "Choose in Finder…" if native else "Browse folders…"
    type_it = "Type a path"
    choices: list[questionary.Choice] = [
        questionary.Choice(f"{_pretty_path(p)}  ({n} session{'s' if n != 1 else ''})", value=str(p))
        for p, n in candidates
    ]
    choices.append(questionary.Choice(browse, value=browse))
    choices.append(questionary.Choice(type_it, value=type_it))
    _reserve_bottom_padding(len(choices) + 3)
    picked = questionary.select(
        "Which folder? (these are where your agents already run)"
        if candidates
        else "Which folder?",
        choices=choices,
    ).ask()
    if picked is None:
        return None
    if picked == browse:
        return _choose_folder_finder(start) if native else _browse_folders(start)
    if picked == type_it:
        typed = questionary.path("Folder path:", only_directories=True).ask()
        if typed is None:
            return None
        folder = Path(typed).expanduser().resolve()
        # An empty answer resolves to the current folder and a typo resolves to
        # a folder no session will ever run in — one records the wrong place,
        # the other records nothing at all, both without saying so.
        if not typed.strip() or not folder.is_dir():
            console.print(
                f"[red]Not a folder: {typed!r}. Nothing was changed — "
                "re-run [bold]stash setup[/bold] to pick again.[/red]"
            )
            raise typer.Exit(1)
        return folder
    return Path(picked)


def _run_setup_wizard() -> None:
    """First-run setup: session recording, agent hooks, folder context, history
    import. Re-runnable anytime via `stash setup` — no answer here is final."""
    cfg = load_config()

    # --- Session recording: always on — the question is WHERE, not whether.
    # (`stash stop` remains the pause switch.) ---
    console.print(
        "\nStash records your coding agent sessions to your private Stash so you\n"
        "and your agents can search them later. Transcripts are visible only to\n"
        "you unless you share them, and you can pause anytime with `stash stop`."
    )
    cwd = Path.cwd()
    everywhere = "Everywhere on this machine"
    here = f"Only this folder ({cwd.name})"
    custom = "Only a folder I pick…"
    # The folders this user's agents already run in go straight into the
    # question — most people should recognize their answer, not produce it.
    inline = [(p, n) for p, n in _agent_folder_candidates(limit=3) if p.resolve() != cwd.resolve()]
    choices: list[questionary.Choice] = [
        questionary.Choice(everywhere, value=everywhere),
        questionary.Choice(here, value=str(cwd)),
        *(
            questionary.Choice(
                f"Only {_pretty_path(p)}  ({n} session{'s' if n != 1 else ''})",
                value=str(p),
            )
            for p, n in inline
        ),
        questionary.Choice(custom, value=custom),
    ]
    _reserve_bottom_padding(len(choices) + 3)
    where = questionary.select(
        "Where should Stash record agent sessions?",
        choices=choices,
        default=everywhere,
    ).ask()
    if where is None:
        raise typer.Exit(1)
    if where == everywhere:
        save_recorded_paths([])
    elif where == custom:
        picked = _pick_record_folder(cwd)
        if picked is None:
            raise typer.Exit(1)
        save_recorded_paths([str(picked)])
    else:
        save_recorded_paths([where])
    start_streaming()

    detected = _detected_agents()
    if detected:
        enabled = load_enabled_agents()
        default_enabled = enabled if enabled is not None else detected

        _reserve_bottom_padding(len(detected) + 6)
        selected = _pick_agents(
            "Which coding agents should Stash record?", detected, default_enabled
        )
        if selected is None:
            raise typer.Exit(1)

        save_enabled_agents(selected)
        _install_all_hooks(selected)
    else:
        save_enabled_agents([])
        console.print(
            "  [yellow]No coding agents found on this machine, so nothing will be\n"
            "  recorded yet. Re-run [bold]stash setup[/bold] after installing one\n"
            "  (Claude Code, Codex, Cursor, opencode, Gemini CLI…).[/yellow]"
        )

    # --- Folder context (any folder works — git repo not required) ---
    repo_root = _git_toplevel() or Path.cwd()
    _reserve_bottom_padding(4)
    connect = questionary.confirm(
        f"Add Stash instructions to CLAUDE.md in {repo_root.name}, so agents "
        "working there know how to use Stash?",
        default=True,
    ).ask()
    if connect is None:
        raise typer.Exit(1)
    if connect:
        _auto_connect_repo(repo_root, cfg)
    else:
        console.print("  [dim]Run stash connect from any project folder later.[/dim]")

    # --- Import historical conversations ---
    _onboarding_import_history(detected)

    _show_setup_complete_splash()


@app.command("setup")
def setup_cmd(
    record: bool | None = typer.Option(
        None,
        "--record/--no-record",
        help="Record agent sessions on this machine (headless mode).",
    ),
    agents: str | None = typer.Option(
        None,
        "--agents",
        help="Comma-separated agents to record, e.g. claude,codex. Requires --record.",
    ),
    connect: bool | None = typer.Option(
        None,
        "--connect/--no-connect",
        help="Add Stash instructions to CLAUDE.md in the current folder (headless mode).",
    ),
    import_history: bool | None = typer.Option(
        None,
        "--import-history/--no-import-history",
        help="Import historical conversations in the background. Requires --record.",
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Run the setup wizard: session recording, agent hooks, folder context.

    Interactive in a terminal. With any flag — or whenever stdin isn't a
    TTY — it runs headless instead, and every decision must arrive as a
    flag. That is the path coding agents drive: ask the setup questions in
    conversation, then run one deterministic command.
    """
    _require_auth()
    telemetry.record("setup")

    headless = (
        any(v is not None for v in (record, agents, connect, import_history))
        or not sys.stdin.isatty()
        or _use_json(as_json)
    )
    if not headless:
        _run_setup_wizard()
        return

    missing = []
    if record is None:
        missing.append("--record/--no-record")
    if connect is None:
        missing.append("--connect/--no-connect")
    if record:
        if agents is None:
            missing.append("--agents")
        if import_history is None:
            missing.append("--import-history/--no-import-history")
    if missing:
        _exit_user_error(
            f"Headless setup needs every decision as an explicit flag. "
            f"Missing: {', '.join(missing)}"
        )
    if not record and (agents is not None or import_history):
        _exit_user_error("--agents and --import-history require --record.")

    _run_setup_headless(record, agents, connect, import_history, use_json=_use_json(as_json))


def _run_setup_headless(
    record: bool,
    agents_csv: str | None,
    connect: bool,
    import_history: bool | None,
    use_json: bool = False,
) -> None:
    """Non-interactive setup: every wizard decision arrives pre-answered.

    Terse ✓-per-step output and no splash — the caller is a coding agent
    relaying to a user, not a person at a terminal. In JSON mode the per-step
    ✓ lines go to stderr and a single result object goes to stdout."""
    if use_json:

        def status(markup: str, plain: str) -> None:
            echo_stderr(plain)
    else:

        def status(markup: str, plain: str) -> None:
            console.print(markup)

    cfg = load_config()

    if record:
        detected = _detected_agents()
        selected = [a.strip() for a in agents_csv.split(",") if a.strip()]
        unknown = sorted(set(selected) - set(detected))
        if not selected or unknown:
            what = f"not detected on this machine: {', '.join(unknown)}" if unknown else "empty"
            _exit_user_error(
                f"--agents is {what}. Detected agents: {', '.join(detected) or 'none'}"
            )
        start_streaming()
        # Headless has no folder-scope flag, so `--record` means this machine.
        # Writing that explicitly is what makes the run deterministic: without
        # it a folder scope left by an earlier `stash setup` would silently
        # survive, and the ✓ below would be describing recording that isn't
        # happening outside that folder.
        save_recorded_paths([])
        save_enabled_agents(selected)
        _install_all_hooks(selected, use_json=use_json)
        status(
            f"  [green]✓[/green] Recording on everywhere on this machine for: {', '.join(selected)}",
            f"  ✓ Recording on everywhere on this machine for: {', '.join(selected)}",
        )
    else:
        stop_streaming()
        status("  [green]✓[/green] Recording off", "  ✓ Recording off")

    if connect:
        _auto_connect_repo(_git_toplevel() or Path.cwd(), cfg, use_json=use_json)
    else:
        status("  [green]✓[/green] Folder context skipped", "  ✓ Folder context skipped")

    if import_history:
        conversations = _conversations_to_import(selected)
        if conversations:
            _spawn_history_import(len(conversations))
        else:
            status("  No historical conversations found.", "  No historical conversations found.")

    if use_json:
        output_json({"ok": True, "record": record, "connect": connect})


@app.command("verify-email")
def verify_email_cmd(as_json: bool = typer.Option(False, "--json")):
    """Email yourself a verification link. Verifying your email is what joins
    you to your company's workspace, if one exists for your email domain."""
    _require_auth()
    with _client() as c:
        try:
            result = c.resend_verification_email()
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "sent_to": result["sent_to"]})
        return
    console.print(
        f"  [green]✓[/green] Verification link sent to [bold]{result['sent_to']}[/bold] — "
        "click it and you're done."
    )


@app.command("connect")
def connect_cmd(as_json: bool = typer.Option(False, "--json")):
    """Add Stash instructions to this folder's CLAUDE.md and enable session uploads.

    Idempotent: if this folder is already connected (a `.stash` manifest
    exists), the command exits 0 and reports the no-op instead of re-writing.
    """
    cfg = _require_auth()
    telemetry.record("connect")

    use_json = _use_json(as_json)
    repo_root = _git_toplevel() or Path.cwd()
    already = (repo_root / MANIFEST_FILE).is_file()
    if not already:
        _auto_connect_repo(repo_root, cfg, use_json=use_json)
    start_streaming()
    if already:
        _report_mutation(use_json, False, "Already connected — nothing to do.")
        return
    _report_mutation(use_json, True, "Connected — Stash context written and streaming enabled.")


@app.command("start")
def start_cmd(as_json: bool = typer.Option(False, "--json")):
    """Resume streaming transcripts globally (undoes `stash stop`)."""
    _require_auth()
    start_streaming()
    if _use_json(as_json):
        output_json({"ok": True, "streaming": True})
        return
    console.print("  [green]✓[/green] Streaming enabled.")


@app.command("stop")
def stop_cmd(as_json: bool = typer.Option(False, "--json")):
    """Stop streaming transcripts globally."""
    _require_auth()
    stop_streaming()
    if _use_json(as_json):
        output_json({"ok": True, "streaming": False})
        return
    console.print("  [green]✓[/green] Streaming stopped.")


# ===========================================================================
# Folder connection: `.stash` manifest + CLAUDE.md context, via `stash connect`
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


def _install_claude_plugin(use_json: bool = False) -> bool:
    """Install the stash plugin for Claude Code via the official marketplace.

    Both subcommands are idempotent — re-running prints a "already added /
    installed" notice rather than failing — so we don't pre-check state.
    Returns True on success, False if either subprocess call errors (errors
    are surfaced to the user inline).
    """
    import subprocess as _sp

    def status(markup: str, plain: str) -> None:
        if use_json:
            echo_stderr(plain)
        else:
            console.print(markup)

    binary = _claude_binary()
    if binary is None:
        if use_json:
            echo_stderr(
                "  Found your Claude Code folder, but no `claude` executable to install "
                "the live-recording plugin with. Past sessions still import; new ones "
                "won't stream until you re-run `stash setup` from a shell where "
                "`claude --version` works."
            )
        else:
            console.print(
                "  [yellow]Found your Claude Code folder, but no `claude` executable to "
                "install the live-recording plugin with. Past sessions still import; new "
                "ones won't stream until you re-run [bold]stash setup[/bold] from a shell "
                "where `claude --version` works.[/yellow]"
            )
        return False

    for cmd in (
        [binary, "plugin", "marketplace", "add", "Fergana-Labs/stash"],
        [binary, "plugin", "install", "stash@stash-plugins"],
    ):
        try:
            result = _sp.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        except _sp.CalledProcessError as e:
            status(
                f"  [yellow]`{' '.join(cmd)}` exited {e.returncode}.[/yellow]",
                f"  `{' '.join(cmd)}` exited {e.returncode}.",
            )
            if e.stderr:
                status(
                    f"  [dim]{e.stderr.strip().splitlines()[-1]}[/dim]",
                    f"  {e.stderr.strip().splitlines()[-1]}",
                )
            return False
        except (FileNotFoundError, _sp.TimeoutExpired) as e:
            status(
                f"  [yellow]Could not run `{' '.join(cmd)}`: {e}[/yellow]",
                f"  Could not run `{' '.join(cmd)}`: {e}",
            )
            return False
        # Surface the success line (last line of stdout, e.g. "Successfully
        # installed plugin: stash@stash-plugins (scope: user)") so the user
        # sees what happened.
        last = (result.stdout or "").strip().splitlines()
        if last:
            status(f"  [green]✓[/green] {last[-1]}", f"  ✓ {last[-1]}")

    if _enable_marketplace_autoupdate(Path.home() / ".claude" / "settings.json"):
        status(
            "  [green]✓[/green] auto-update enabled for the stash-plugins marketplace",
            "  ✓ auto-update enabled for the stash-plugins marketplace",
        )
    else:
        status(
            "  [yellow]Could not update ~/.claude/settings.json — enable auto-update "
            "manually: /plugin → Marketplaces → stash-plugins → Enable auto-update. "
            "Without it the plugin never updates itself.[/yellow]",
            "  Could not update ~/.claude/settings.json — enable auto-update manually: "
            "/plugin → Marketplaces → stash-plugins → Enable auto-update. "
            "Without it the plugin never updates itself.",
        )

    # Freshen right now regardless: until this run set autoUpdate (or on Claude
    # Code versions that ignore the key at user scope), the marketplace clone
    # and plugin may be weeks stale. Best-effort — a failure here still leaves
    # a working install, and the plugin's session-start drift warning names any
    # remaining staleness.
    for cmd in (
        [binary, "plugin", "marketplace", "update", "stash-plugins"],
        [binary, "plugin", "update", "stash@stash-plugins"],
    ):
        try:
            _sp.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except (_sp.CalledProcessError, FileNotFoundError, _sp.TimeoutExpired) as e:
            status(
                f"  [yellow]`{' '.join(cmd)}` failed: {e}[/yellow]",
                f"  `{' '.join(cmd)}` failed: {e}",
            )
            break
    else:
        status(
            "  [green]✓[/green] marketplace and plugin updated to latest",
            "  ✓ marketplace and plugin updated to latest",
        )
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


IMPORT_STATUS_FILE = Path.home() / ".stash" / "import-history.json"
IMPORT_LOG_FILE = Path.home() / ".stash" / "import-history.log"


def _write_import_status(total: int, done: int, errors: int, finished: bool) -> None:
    import os

    IMPORT_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace: `--status` follows this file live and must never read a
    # half-written JSON.
    tmp = IMPORT_STATUS_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(
            {
                "total": total,
                "done": done,
                "errors": errors,
                "finished": finished,
                "updated_at": time.time(),
            }
        )
        + "\n"
    )
    os.replace(tmp, IMPORT_STATUS_FILE)


def _spawn_history_import(count: int) -> None:
    """Kick off the history import as a detached `stash import-history`
    process — thousands of uploads must not hold setup hostage."""
    import subprocess as _sp

    # Seed the status file so the setup-complete splash can show the import
    # immediately; the spawned process takes over updating it.
    _write_import_status(total=count, done=0, errors=0, finished=False)

    IMPORT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(IMPORT_LOG_FILE, "ab") as log:
        _sp.Popen(
            [sys.argv[0], "import-history"],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    console.print(
        f"  [green]✓[/green] Importing {count} conversations in the background.\n"
        "    [dim]Check on it anytime: stash import-history --status[/dim]"
    )


def _conversations_to_import(agents: list[str] | None) -> list:
    """Past conversations the recording scope covers.

    Importing is recording, backwards: a user who answered "only this folder"
    must not have every other folder's history uploaded behind that answer.
    `recorded_paths` is the same list the plugin's live gate reads, so past and
    future sessions obey one setting."""
    from .import_history import discover_conversations

    recorded = [p for p in (load_config().get("recorded_paths") or []) if p]
    if not recorded:
        return discover_conversations(agents)

    seen: set[tuple[str, str]] = set()
    scoped = []
    for folder in recorded:
        for conv in discover_conversations(agents, repo_dir=folder):
            if (conv.agent, conv.session_id) in seen:
                continue
            seen.add((conv.agent, conv.session_id))
            scoped.append(conv)
    return scoped


def _onboarding_import_history(detected_agents: list[str]) -> None:
    """Offer to import historical conversations during onboarding."""
    from .import_history import summarize_discovery

    agents = detected_agents or None
    conversations = _conversations_to_import(agents)
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
        f"Import {len(conversations)} historical conversations? (runs in the background)",
        default=True,
    ).ask()
    if not ok:
        return

    _spawn_history_import(len(conversations))


def _show_import_status(use_json: bool = False) -> None:
    """Follow a running import with a live progress bar; print a summary when
    it's already finished or stalled. Ctrl-C detaches without stopping it.
    In JSON mode, emit a status object and skip the live progress bar."""
    from rich.progress import Progress

    if not IMPORT_STATUS_FILE.exists():
        if use_json:
            output_json({"status": "no_import", "done": 0, "total": 0, "errors": 0})
            return
        console.print("No import has run on this machine.")
        return

    s = json.loads(IMPORT_STATUS_FILE.read_text())
    stalled = not s["finished"] and time.time() - s["updated_at"] > 3600
    if use_json:
        state = "finished" if s["finished"] else ("stalled" if stalled else "running")
        output_json(
            {
                "status": state,
                "done": s["done"],
                "total": s["total"],
                "errors": s["errors"],
            }
        )
        return
    if s["finished"] or stalled:
        state = "finished" if s["finished"] else "stalled — re-run stash import-history to resume"
        console.print(f"  {s['done']}/{s['total']} conversations, {s['errors']} errors — {state}")
        return

    try:
        with Progress(console=console) as progress:
            task = progress.add_task("Importing…", total=s["total"])
            while not s["finished"]:
                s = json.loads(IMPORT_STATUS_FILE.read_text())
                progress.update(task, completed=s["done"], total=s["total"])
                time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("  [dim]Detached — the import keeps running in the background.[/dim]")
        return
    if s["errors"]:
        console.print(f"  [yellow]{s['errors']} conversations failed[/yellow]")


@app.command("import-history")
def import_history_cmd(
    status: bool = typer.Option(
        False, "--status", help="Show progress of the running or last-finished import."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Import all historical agent conversations into your Stash.

    Scoped to the folders you chose to record (`recorded_paths`), so the import
    covers exactly what live recording covers. Safe to re-run: the server skips
    sessions that already exist. The setup wizard launches this as a background
    process; run it directly to import in the foreground with a progress bar."""
    use_json = _use_json(as_json)

    if status:
        _show_import_status(use_json)
        return

    _require_auth()
    telemetry.record("import_history")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    from rich.progress import Progress

    from .import_history import upload_conversation

    conversations = _conversations_to_import(load_enabled_agents() or None)
    if not conversations:
        if use_json:
            output_json({"ok": True, "imported": 0, "errors": 0, "total": 0})
            return
        console.print("No historical conversations found.")
        return

    total = len(conversations)
    done = 0
    errors = 0
    last_error = ""
    _write_import_status(total=total, done=0, errors=0, finished=False)

    if use_json:
        # httpx.Client is thread-safe; sequential uploads were taking >1h for a
        # machine with a few thousand conversations.
        with _client() as c:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(upload_conversation, c, conv) for conv in conversations]
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except (StashError, httpx.HTTPError) as e:
                        errors += 1
                        last_error = str(e)
                    done += 1
                    if done % 25 == 0 or done == total:
                        _write_import_status(
                            total=total, done=done, errors=errors, finished=done == total
                        )
        output_json({"ok": True, "imported": done - errors, "errors": errors, "total": total})
        return

    # httpx.Client is thread-safe; sequential uploads were taking >1h for a
    # machine with a few thousand conversations.
    with _client() as c, Progress(console=console) as progress:
        task = progress.add_task("Importing…", total=total)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(upload_conversation, c, conv) for conv in conversations]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except (StashError, httpx.HTTPError) as e:
                    errors += 1
                    last_error = str(e)
                done += 1
                progress.advance(task)
                if done % 25 == 0 or done == total:
                    _write_import_status(
                        total=total, done=done, errors=errors, finished=done == total
                    )

    console.print(f"  [green]✓[/green] Imported {done - errors} conversations")
    if errors:
        echo_stderr(f"  {errors} failed — last error: {last_error}")


def _active_import() -> dict | None:
    """The in-flight history import's status, or None when there isn't one.

    A status file that stopped updating an hour ago means the import process
    died — don't claim it's still uploading."""
    if not IMPORT_STATUS_FILE.exists():
        return None
    status = json.loads(IMPORT_STATUS_FILE.read_text())
    if status["finished"] or time.time() - status["updated_at"] > 3600:
        return None
    return status


def _setup_complete_intro(
    frontend_url: str,
    connected: bool,
    recording: bool,
    importing: dict | None,
    recorded_paths: list[str] | None = None,
) -> str:
    # Home *is* the memory dashboard — there is no /memory route.
    memory_url = frontend_url
    # Empty = everywhere, the contract `recorded_paths` carries everywhere else
    # (cli/config.py, the plugin's gate). The splash has to say which one the
    # user just chose — promising machine-wide capture to someone who scoped
    # recording to one folder is the setup lying about what it did.
    scope = ", ".join(_pretty_path(Path(p)) for p in recorded_paths or [])
    where = f"in {scope}" if scope else "on this machine"
    recording_section = (
        "[bold]You're recording[/bold]\n"
        f"Agent sessions {where} upload to your private Stash.\n"
        "[dim]Pause with stash stop, change folders with stash setup[/dim]"
        if recording
        else "[bold]Recording is off[/bold]\n"
        "Turn it on anytime with [cyan]stash start[/cyan] or [cyan]stash setup[/cyan]."
    )
    importing_section = (
        ""
        if importing is None
        else "\n\n[bold]Your history is uploading right now[/bold]\n"
        f"{importing['total']} past conversations are importing in the background —\n"
        "watch your knowledge base fill up.\n"
        "[dim]Live progress: stash import-history --status[/dim]"
    )
    connect_section = (
        ""
        if connected
        else "\n\n[bold]Set up a project[/bold]\n"
        "Run [cyan]stash connect[/cyan] in a project folder to add Stash instructions\n"
        "to its CLAUDE.md — agents working there will know how to use your Stash."
    )
    return (
        "[bold]Your agents just got a memory[/bold]\n"
        f"Every coding session {where} now lands in your private Stash.\n"
        "Your agents can draw on everything you've worked on before — past fixes,\n"
        "decisions, dead ends — instead of starting every session from zero.\n"
        "\n"
        "[bold]Your knowledge base[/bold]\n"
        f"  [link={memory_url}][bold #1e3a8a]{memory_url}[/bold #1e3a8a][/link]\n"
        "Stash compiles your sessions into memory your agents check before they\n"
        "work. The more you use it, the better they get.\n"
        "\n"
        f"{recording_section}"
        f"{importing_section}"
        f"{connect_section}"
    )


def _show_setup_complete_splash() -> None:
    """Show a success splash after first-run login. Never clears the screen —
    errors printed by earlier steps must stay visible."""
    octopus = textwrap.dedent(STASH_OCTOPUS.strip("\n"))
    logo = textwrap.dedent(STASH_LOGO.strip("\n"))
    console.print()
    console.print(Align.center(Text.from_markup(f"[bold #F97316]{octopus}[/bold #F97316]")))
    console.print()
    console.print(Align.center(Text.from_markup(f"[bold #1e3a8a]{logo}[/bold #1e3a8a]")))
    console.print("  [bold green]You're all set up.[/bold green]\n")

    connected = load_manifest() is not None
    recording = not streaming_stopped()
    console.print(
        Panel(
            Text.from_markup(
                _setup_complete_intro(
                    _frontend_base_url(),
                    connected,
                    recording,
                    _active_import(),
                    load_config().get("recorded_paths"),
                )
            ),
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
def welcome_cmd(as_json: bool = typer.Option(False, "--json")):
    """Show the post-install welcome splash."""
    if _use_json(as_json):
        # The splash is rich human text with no machine-parseable payload;
        # JSON mode emits a simple acknowledgement on stdout instead.
        output_json({"ok": True})
        return
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
    "openclaw": Path.home() / ".stash/plugins/openclaw",
    "hermes": Path.home() / ".stash/plugins/hermes",
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
    if not snapshot:
        print_empty_state("local agent plugins")
        if _use_json(as_json):
            output_json({"upload_health": snapshot})
        return
    if _use_json(as_json):
        output_json({"upload_health": snapshot})
        return

    console.print("[bold]Stash upload status[/bold]\n")
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

    if _use_json(as_json):
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
            selected = _pick_agents(
                "Which coding agents should stream to Stash?", detected, current_enabled
            )
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


workspace_app = typer.Typer(help="Choose which scope your sessions and searches use.")
app.add_typer(workspace_app, name="workspace")


@workspace_app.command("list")
def workspace_list(as_json: bool = typer.Option(False, "--json")):
    """List workspaces you're a member of, marking the active scope."""
    active = load_config().get("scope", "")
    with _client() as c:
        try:
            data = c.list_workspaces()
        except StashError as e:
            _err(e)
    workspaces = data["workspaces"]
    pending = data.get("pending_domain_workspaces", [])
    if not workspaces and not pending:
        print_empty_state("workspaces")
    if _use_json(as_json):
        output_json(
            {
                "workspaces": workspaces,
                "pending_domain_workspaces": pending,
                "active_scope": active or None,
            }
        )
        return
    marker = " [green]*[/green]" if not active else ""
    console.print(f"  [bold]personal[/bold]{marker}")
    for ws in workspaces:
        marker = " [green]*[/green]" if ws["scope_user_id"] == active else ""
        console.print(f"  [bold]{ws['name']}[/bold]  [dim]{ws['domain']}[/dim]{marker}")
    for ws in pending:
        console.print(
            f"  [yellow]{ws['name']}[/yellow]  [dim]{ws['domain']}[/dim]  "
            "[yellow]— joins once your email is verified: run "
            "[cyan]stash verify-email[/cyan] and click the link we send[/yellow]"
        )


@workspace_app.command("switch")
def workspace_switch(
    name: str = typer.Argument(..., help="Workspace name or domain, or 'personal'."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Route sessions, events, transcripts, and searches to this scope.

    Applies everywhere the CLI and agent plugins write — the next agent
    session lands in the chosen scope, and `stash search` reads from it.
    """
    use_json = _use_json(as_json)
    if name == "personal":
        save_scope(None)
        if use_json:
            output_json({"ok": True, "workspace": "personal"})
            return
        console.print("[green]Switched[/green] to your personal scope.")
        return

    with _client() as c:
        try:
            data = c.list_workspaces()
        except StashError as e:
            _err(e)
    workspaces = data["workspaces"]
    match = next(
        (ws for ws in workspaces if name in (ws["name"], ws["domain"])),
        None,
    )
    if match is None:
        pending = next(
            (
                ws
                for ws in data.get("pending_domain_workspaces", [])
                if name in (ws["name"], ws["domain"])
            ),
            None,
        )
        if pending:
            _exit_user_error(
                f"'{pending['name']}' matches your email domain — you'll join it as "
                "soon as your email is verified. Run `stash verify-email`, click the "
                "link we send, then try again."
            )
        known = ", ".join(ws["name"] for ws in workspaces) or "(none)"
        _exit_user_error(f"no workspace named '{name}'. You belong to: {known}")
    save_scope(str(match["scope_user_id"]))
    if use_json:
        output_json({"ok": True, "workspace": match["name"]})
        return
    console.print(
        f"[green]Switched[/green] to [bold]{match['name']}[/bold] — new agent sessions "
        "and searches use this workspace. `stash workspace switch personal` to go back."
    )


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
    if not keys:
        print_empty_state("API keys")
    if _use_json(as_json):
        output_json(keys)
        return
    for k in keys:
        last = k.get("last_used_at") or "never"
        console.print(
            f"  [bold]{k['name']}[/bold]  "
            f"[dim]id: {k['id']}  created: {str(k['created_at'])[:10]}  "
            f"last used: {str(last)[:10]}[/dim]"
        )


@keys_app.command("revoke")
def keys_revoke(
    key_id: str = typer.Argument(..., help="Key id to revoke."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Revoke an API key by id. Any device using it will 401 on next call."""
    with _client() as c:
        try:
            c.revoke_api_key(key_id)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "key_id": key_id})
        return
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
def disconnect_cmd(as_json: bool = typer.Option(False, "--json")):
    """Disconnect this repo from Stash. Removes the .stash file.

    Idempotent: a repo with no `.stash` file is already disconnected — the
    command exits 0 and reports the no-op.
    """
    repo_root = _git_toplevel()
    if not repo_root:
        _exit_user_error("Not inside a git repo.")

    use_json = _use_json(as_json)
    manifest_path = repo_root / MANIFEST_FILE
    if not manifest_path.is_file():
        _report_mutation(use_json, False, "Not connected — nothing to remove.")
        return

    # Streaming is global to the user's scope, so disconnecting one repo leaves it
    # untouched — run `stash stop` to halt streaming everywhere.
    manifest_path.unlink()
    _report_mutation(
        use_json,
        True,
        f"Removed {MANIFEST_FILE} — repo disconnected.",
        markup=f"  [green]✓[/green] Removed [cyan]{MANIFEST_FILE}[/cyan] — repo disconnected.",
    )


@app.command("vfs", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def vfs_command(
    ctx: typer.Context,
    cwd: str = typer.Option("/", "--cwd", help="Virtual working directory."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Run bash-shaped commands against Stash sources."""
    from stashvfs import MountError, SkillAppVfsShell, StashVfsModel

    use_json = _use_json(as_json)
    cfg = load_config()
    if not cfg.get("api_key"):
        _exit_user_error("Not signed in. Run [bold]stash signin[/bold] first.")

    client = StashClient(base_url=cfg["base_url"], api_key=cfg["api_key"])
    try:
        model = StashVfsModel(client, include_computer=True)
        model.refresh()
        shell = SkillAppVfsShell(model, cwd=cwd)

        command = " ".join(ctx.args).strip()
        if not command:
            _exit_user_error('Usage: stash vfs "<command>" (e.g. [bold]stash vfs "ls /me"[/bold]).')

        result = shell.run(command)
        if use_json:
            output_json(
                {
                    "ok": result.exit_code == 0,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
        else:
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
        if result.exit_code:
            raise typer.Exit(result.exit_code)
    except MountError as e:
        _exit_user_error(str(e))
    finally:
        client.close()


@app.command("sql")
def sql_command(
    query: str = typer.Argument(..., help='e.g. "SELECT * FROM jobs WHERE salary > 90000"'),
    as_json: bool = typer.Option(False, "--json"),
):
    """Query your tables with read-only SQL (DuckDB's Postgres-flavored dialect).

    A table is addressable by bare name when unique ("SELECT * FROM jobs") and
    always by its folder path as the schema ('SELECT * FROM "files/Hiring".jobs').
    Explore with information_schema.tables / information_schema.columns.
    """
    with _client() as c:
        try:
            result = c.run_sql(query)
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(result)
        return
    names = [col["name"] for col in result["columns"]]
    rendered = [["" if v is None else str(v) for v in row] for row in result["rows"]]
    widths = [
        max(len(name), *(len(row[i]) for row in rendered)) if rendered else len(name)
        for i, name in enumerate(names)
    ]
    print(" | ".join(name.ljust(w) for name, w in zip(names, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in rendered:
        print(" | ".join(value.ljust(w) for value, w in zip(row, widths)))
    print(f"({result['row_count']} rows)")
    if result["truncated"]:
        console.print("[yellow]Result truncated — add a LIMIT or tighter WHERE.[/yellow]")


def _read_vfs_raw(path: str) -> bytes:
    """The original bytes behind a VFS path — a connected-source document comes
    back verbatim from the provider (the PDF itself, not its extracted text)."""
    from stashvfs import MountError, StashVfsModel, VfsClientError

    client = _client()
    try:
        model = StashVfsModel(client, include_computer=True)
        model.refresh()
        return model.read_raw(path)
    except FileNotFoundError:
        console.print(f"[red]No such file: {path}[/red]")
        raise typer.Exit(1) from None
    except IsADirectoryError:
        console.print(f"[red]Is a directory: {path}[/red]")
        raise typer.Exit(1) from None
    except (MountError, VfsClientError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    finally:
        client.close()


@app.command("download")
def download_command(
    path: str = typer.Argument(
        ..., help="VFS path (e.g. '/sources/google/Part Catalogs/bendix.pdf')."
    ),
    output: str = typer.Option(
        None, "--output", "-o", help="Destination path. Defaults to the file's name in cwd."
    ),
    as_json: bool = typer.Option(False, "--json"),
):
    """Download the original bytes behind a VFS path.

    `stash vfs cat` shows a document's extracted text; this fetches the file
    itself. Use it when your harness can read PDFs and images directly —
    download the document, then read it with your own file tools to see
    figures, diagrams, scans, and table layout with your own eyes.
    """
    data = _read_vfs_raw(path)
    dest = Path(output) if output else Path(posixpath.basename(path.rstrip("/")))
    dest.write_bytes(data)
    if _use_json(as_json):
        output_json({"ok": True, "path": str(dest.resolve()), "bytes": len(data)})
        return
    console.print(
        f"[green]Downloaded[/green] {path} → {dest.resolve()} [dim]{len(data)} bytes[/dim]"
    )


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
- `stash share` — freeze this coding session (transcript + the files it
  touched) into a Skill folder; `--session "<title>"` picks another one
  by the title search and the VFS show. Sessions are inherently a
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
- `stash vfs "cat '/files/README.md'"`

Anti-pattern: minting one Stash per file you happen to share. Skills
exist to group related things; one item per Stash defeats the model and
clutters Discover.
"""


@prompts_app.command("agent-guidance")
def prompts_agent_guidance(as_json: bool = typer.Option(False, "--json")):
    """Print the canonical 'what is a Skill + when to create one' prompt.

    Intended for coding agents (Claude Code, Codex, Cursor, etc.) to
    re-inject when they want to remember the model mid-session."""
    if _use_json(as_json):
        output_json({"prompt": AGENT_GUIDANCE_PROMPT})
        return
    console.print(AGENT_GUIDANCE_PROMPT)


# ===========================================================================
# Tools — per-user MCP server registry (`stash tools ...`)
# ===========================================================================

tools_app = typer.Typer(
    help="Register MCP servers in Stash and install them into Claude Code projects."
)
app.add_typer(tools_app, name="tools")

# Top-level key in .mcp.json listing the server names stash owns. Claude Code
# only reads mcpServers, so the marker rides along untouched; install sweeps
# and rewrites marked entries but never touches user-added ones.
STASH_MANAGED_MCP_KEY = "stashManagedServers"


def _parse_kv_pairs(pairs: list[str], flag: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not key or not sep:
            console.print(f"[red]{flag} expects KEY=VAL, got {pair!r}[/red]")
            raise typer.Exit(1)
        out[key] = value
    return out


def _mcp_json_entry(server: dict) -> dict:
    """One registered server as a Claude Code mcpServers entry."""
    import shlex

    if server["transport"] == "stdio":
        parts = shlex.split(server["command"])
        entry: dict = {"type": "stdio", "command": parts[0], "args": parts[1:]}
        if server.get("env"):
            entry["env"] = server["env"]
        return entry
    entry = {"type": "http", "url": server["url"]}
    if server.get("headers"):
        entry["headers"] = server["headers"]
    return entry


def _merge_mcp_server(dest: Path, name: str, entry: dict) -> str:
    """Merge one stash-managed server entry into a project .mcp.json.

    Same discipline as _merge_json_hooks: user entries are never touched, and
    re-runs are idempotent. Ownership is tracked in STASH_MANAGED_MCP_KEY, so
    a user entry that happens to share the name is a conflict, not a clobber.
    Returns 'installed', 'skipped', 'conflict', or 'failed'.
    """
    if dest.exists():
        try:
            config = json.loads(dest.read_text())
        except json.JSONDecodeError:
            return "failed"
    else:
        config = {}

    servers = config.setdefault("mcpServers", {})
    managed = config.setdefault(STASH_MANAGED_MCP_KEY, [])
    if name in servers and name not in managed:
        return "conflict"
    if servers.get(name) == entry and name in managed:
        return "skipped"

    servers[name] = entry
    if name not in managed:
        managed.append(name)
        managed.sort()
    dest.write_text(json.dumps(config, indent=2) + "\n")
    return "installed"


def _find_mcp_server(servers: list, name: str) -> dict:
    for server in servers:
        if server["name"] == name:
            return server
    console.print(f"[red]No MCP server named {name!r}. `stash tools list` shows yours.[/red]")
    raise typer.Exit(1)


@tools_app.command("add")
def tools_add(
    name: str = typer.Argument(..., help="Server name (becomes the mcpServers key)."),
    command: str = typer.Option("", "--command", help="stdio server launch command."),
    url: str = typer.Option("", "--url", help="http server URL."),
    header: list[str] = typer.Option(
        [], "--header", help="http request header, KEY=VAL (repeatable)."
    ),
    env: list[str] = typer.Option([], "--env", help="stdio env var, KEY=VAL (repeatable)."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Register an MCP server (--command for stdio, --url for http)."""
    if bool(command) == bool(url):
        _exit_user_error("Pass exactly one of --command (stdio) or --url (http).")
    with _client() as c:
        try:
            server = c.create_mcp_server(
                name,
                "stdio" if command else "http",
                command=command or None,
                url=url or None,
                headers=_parse_kv_pairs(header, "--header"),
                env=_parse_kv_pairs(env, "--env"),
            )
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json(server)
        return
    target = server["command"] or server["url"]
    console.print(f"Added [bold]{server['name']}[/bold] ({server['transport']}: {target})")
    console.print(f"[dim]`stash tools install {server['name']}` wires it into this project.[/dim]")


@tools_app.command("list")
def tools_list(as_json: bool = typer.Option(False, "--json")):
    """List your registered MCP servers."""
    with _client() as c:
        try:
            servers = c.list_mcp_servers()
        except StashError as e:
            _err(e)
    if not servers:
        print_empty_state("MCP servers")
    if _use_json(as_json):
        output_json({"servers": servers})
        return
    for s in servers:
        target = s["command"] or s["url"]
        console.print(f"  [bold]{s['name']}[/bold]  [dim]{s['transport']}: {target}[/dim]")


@tools_app.command("remove")
def tools_remove(name: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Remove a registered MCP server."""
    with _client() as c:
        try:
            server = _find_mcp_server(c.list_mcp_servers(), name)
            c.delete_mcp_server(server["id"])
        except StashError as e:
            _err(e)
    if _use_json(as_json):
        output_json({"ok": True, "name": name})
        return
    console.print(f"Removed [bold]{name}[/bold]")


@tools_app.command("install")
def tools_install(name: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    """Write a registered server into this project's .mcp.json for Claude Code."""
    with _client() as c:
        try:
            server = _find_mcp_server(c.list_mcp_servers(), name)
        except StashError as e:
            _err(e)
    dest = Path.cwd() / ".mcp.json"
    status = _merge_mcp_server(dest, name, _mcp_json_entry(server))
    if status == "conflict":
        _exit_user_error(
            f"{dest} already has a user-defined server named {name!r}; remove it there first."
        )
    if status == "failed":
        _exit_user_error(f"{dest} is not valid JSON; fix or delete it first.")
    if _use_json(as_json):
        output_json({"ok": True, "name": name, "status": status})
        return
    verb = "Installed" if status == "installed" else "Already up to date:"
    console.print(f"{verb} [bold]{name}[/bold] → {dest}")


def main() -> None:
    """Top-level entry boundary for the `stash` console script.

    Invokes the Typer app with ``standalone_mode=False`` so exceptions are not
    swallowed by Click's default handler; the returned exit code becomes the
    process exit code. Any ``StashError`` that escapes a command body (e.g. a
    wrapped transport error re-raised by a share/page-create site, or a raw
    ``httpx.TransportError`` off the request layer) is routed through the same
    classification and stderr emission as ``_err``, so a backend-delivery
    failure exits with the internal-error code (2) and never leaks to stdout.
    A Click usage error (missing/extra required argument or option) raised
    during parsing is rendered by Click's own ``show()`` (its canonical
    stderr formatter, which ``standalone_mode=False`` otherwise bypasses) and
    exits with Click's usage-error code (2). Any other exception re-raises so
    genuine bugs still show a traceback.
    """
    try:
        code = app(standalone_mode=False)
    except StashError as e:
        _emit_cli_error(
            e.status_code, e.detail, is_internal=classify_error(e) == EXIT_INTERNAL_ERROR
        )
        raise SystemExit(classify_error(e))
    except httpx.TransportError as e:
        _emit_cli_error(TRANSPORT_ERROR_STATUS, str(e), is_internal=True)
        raise SystemExit(EXIT_INTERNAL_ERROR)
    except click.exceptions.UsageError as e:
        e.show()
        raise SystemExit(e.exit_code)
    raise SystemExit(code or 0)


if __name__ == "__main__":
    main()
