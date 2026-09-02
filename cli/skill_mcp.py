"""Tool servers that installed skills declare, written into each harness.

A skill can carry one `mcp: <name> <url>` line in its SKILL.md frontmatter.
That is the whole contract: the server is hosted (streamable HTTP) and takes
the user's Stash API key as a bearer token. On every `stash skills sync` —
which the plugin runs at session start — the local skills directory is read,
each declared server is written into the config of every harness present on
this machine, and servers no longer declared by any skill are removed again.

The set of names this module has written is remembered per skills root, so
it only ever removes what it added and never touches a server the user
configured by hand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .config import USER_CONFIG_DIR, load_config

_DECLARATION_RE = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9_-]{0,99})\s+(https?://\S+)$")

_CODEX_BEGIN = "# stash-skill-servers:begin"
_CODEX_END = "# stash-skill-servers:end"


def _frontmatter(markdown: str) -> dict[str, str]:
    if not markdown.startswith("---\n") or "\n---" not in markdown[4:]:
        return {}
    raw = markdown[4 : markdown.find("\n---", 4)]
    out: dict[str, str] = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            out[key.strip()] = value.strip().strip('"')
    return out


def declared_servers(root: Path) -> tuple[dict[str, str], list[str]]:
    """(name -> url) across every skill under `root`, plus notes for
    declarations that could not be read. A bad line in one skill is
    reported, not allowed to take the other skills' tools down with it."""
    servers: dict[str, str] = {}
    notes: list[str] = []
    if not root.is_dir():
        return servers, notes
    for skill_dir in sorted(root.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_md.exists():
            continue
        value = _frontmatter(skill_md.read_text(encoding="utf-8")).get("mcp", "")
        if not value:
            continue
        match = _DECLARATION_RE.match(value)
        if match is None:
            notes.append(f"{skill_dir.name}: unreadable mcp declaration {value!r}")
            continue
        servers[match.group(1)] = match.group(2)
    return servers, notes


# ── Per-harness writers ────────────────────────────────────────────────
# Each takes the full desired set plus the names this module wrote last time,
# removes stale ones, upserts current ones, and leaves everything else alone.


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# `servers` maps a name to (url, bearer-or-None): the user's key goes only to
# the Stash API itself. Anyone can publish a skill, so a declared server on
# any other host is just a server and never receives the credential.
Servers = dict[str, tuple[str, str | None]]


def _with_headers(base: dict, bearer: str | None) -> dict:
    if bearer is None:
        return base
    return {**base, "headers": {"Authorization": bearer}}


def _json_servers(path: Path, key: str, servers: Servers, owned: set[str], entry) -> None:
    data = _read_json(path)
    table = data.get(key, {})
    for name in owned - set(servers):
        table.pop(name, None)
    for name, (url, bearer) in servers.items():
        table[name] = _with_headers(entry(url), bearer)
    data[key] = table
    _write_json(path, data)


def _write_claude(servers: Servers, owned: set[str]) -> None:
    _json_servers(
        Path.home() / ".claude.json",
        "mcpServers",
        servers,
        owned,
        lambda url: {"type": "http", "url": url},
    )


def _write_cursor(servers: Servers, owned: set[str]) -> None:
    _json_servers(
        Path.home() / ".cursor" / "mcp.json", "mcpServers", servers, owned, lambda url: {"url": url}
    )


def _write_gemini(servers: Servers, owned: set[str]) -> None:
    _json_servers(
        Path.home() / ".gemini" / "settings.json",
        "mcpServers",
        servers,
        owned,
        lambda url: {"httpUrl": url},
    )


def _write_opencode(servers: Servers, owned: set[str]) -> None:
    _json_servers(
        Path.home() / ".config" / "opencode" / "opencode.json",
        "mcp",
        servers,
        owned,
        lambda url: {"type": "remote", "url": url, "enabled": True},
    )


def _write_codex(servers: Servers, owned: set[str]) -> None:
    """Codex reads TOML; the servers live in one marked block that is
    replaced wholesale, so re-runs never duplicate and user config outside
    the markers is untouched."""
    path = Path.home() / ".codex" / "config.toml"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if _CODEX_BEGIN in existing and _CODEX_END in existing:
        head, rest = existing.split(_CODEX_BEGIN, 1)
        _, tail = rest.split(_CODEX_END, 1)
        existing = head.rstrip("\n") + tail
    if not servers:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(existing, encoding="utf-8")
        return
    lines = [_CODEX_BEGIN]
    for name, (url, bearer) in servers.items():
        lines += [f"[mcp_servers.{name}]", f"url = {json.dumps(url)}"]
        if bearer is not None:
            lines.append(f"http_headers = {{ Authorization = {json.dumps(bearer)} }}")
        lines.append("")
    lines.append(_CODEX_END)
    sep = "\n" if existing and not existing.endswith("\n") else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{existing}{sep}\n" + "\n".join(lines) + "\n", encoding="utf-8")


_WRITERS = {
    "claude": _write_claude,
    "cursor": _write_cursor,
    "codex": _write_codex,
    "opencode": _write_opencode,
    "gemini": _write_gemini,
}


# ── Entry point ────────────────────────────────────────────────────────


def _state_path(root: Path) -> Path:
    return (
        USER_CONFIG_DIR
        / "skill_servers"
        / (root.resolve().as_posix().strip("/").replace("/", "_") + ".json")
    )


def sync(root: Path, agents: list[str]) -> list[str]:
    """Bring every present harness's MCP config in line with what the skills
    under `root` declare. Returns human-readable notes."""
    servers, notes = declared_servers(root)
    state_path = _state_path(root)
    owned = set(_read_json(state_path).get("names", []))
    if not servers and not owned:
        return notes

    config = load_config()
    own_api = urlparse(config["base_url"])
    resolved: Servers = {}
    for name, url in servers.items():
        parsed = urlparse(url)
        ours = (parsed.scheme, parsed.netloc) == (own_api.scheme, own_api.netloc)
        if ours and not config["api_key"]:
            raise RuntimeError(
                "not signed in: run `stash signin` before syncing skill tool servers"
            )
        resolved[name] = (url, f"Bearer {config['api_key']}" if ours else None)

    written = [agent for agent in agents if agent in _WRITERS]
    for agent in written:
        _WRITERS[agent](resolved, owned)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"names": sorted(servers)}) + "\n", encoding="utf-8")

    for name, url in servers.items():
        notes.append(f"tool server {name} → {url} ({', '.join(written) or 'no harness found'})")
    for name in sorted(owned - set(servers)):
        notes.append(f"tool server {name} removed")
    return notes
