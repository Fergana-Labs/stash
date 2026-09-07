# Stash Plugin for Pi

Streams Pi coding sessions to Stash using Pi's native `~/.pi/hooks/` system.

## Prerequisites

- `stash` CLI installed and logged in
- `.stash` manifest present in repo (or ancestor)
- Python 3.10+ and `httpx`
- Pi installed with hook directory support (`~/.pi/hooks/`)

## Install

The recommended way to install the Pi hooks is through the `stash` CLI, which
supersedes the manual instructions below: `stash settings` (or the interactive
`stash connect` flow) detects Pi on your machine and copies the self-contained
hook runtime into `~/.pi/` (`_run.sh`, `scripts/hooks/*`, and the `on_*.py`
handlers) from the shipped assets under `stashai/plugin/assets/pi/`. No
symlinks are created, so the install keeps working even if the stash checkout
or pipx env moves, and it never depends on this repo's location.

Manual install (fallback, when you cannot run the CLI installer):

```bash
cd path/to/stash/plugins/pi-plugin
export PLUGIN_ROOT=$(pwd)
mkdir -p ~/.pi/hooks

# Symlink each hook wrapper (symlinks auto-update when you pull the repo)
ln -sf "$PLUGIN_ROOT/scripts/hooks/"* ~/.pi/hooks/

# Agent context — tells Pi it has the stash CLI available
cat AGENTS.md >> ~/.pi/AGENTS.md
```

Note that the manual symlink path points at this checkout, so it breaks if the
repo moves; prefer the CLI installer which copies the runtime into `~/.pi/`.

## How Pi hooks work

Pi reads executable files from `~/.pi/hooks/` — one file per event name.
Each hook receives JSON on stdin with the event payload and must exit
with status 0. The hook files in `scripts/hooks/` are thin bash wrappers
that delegate to `_run.sh`, which resolves the correct Python interpreter
and dispatches to the corresponding `on_*.py` handler.

## Commands

Everything is a plain `stash` CLI subcommand — no slash commands or skills:

| Command | Description |
|---------|-------------|
| `stash connect` | Interactive setup (auth + store) |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

## What streams

| Pi event | Stash event | Notes |
|---|---|---|
| `session_start` | — (warms cache) | Session record created, skills synced |
| `user_message` | `user_message` | User prompt streamed |
| `tool_use` | `tool_use` | Tool invocations streamed (bash, read, write, edit, grep, …) |
| `assistant_message` | `assistant_message` + transcript upload | Per-turn assistant response; transcript uploaded in background with 60s cooldown |
| `session_end` | `session_end` | Session finalized, state cleared |

## Known gaps

1. **Pi hook coverage depends on Pi's runtime.** Pi's hook system is still
   maturing. Check Pi's documentation for which events fire reliably and
   whether all tool types are covered.
2. **macOS / Linux only.** Pi runs on macOS and Linux. No Windows support.
   (Consistent with all existing Stash streaming plugins.)

## Retrieval

Pi has shell access. For reads mid-conversation, have the agent invoke
the `stash` CLI. Use `stash vfs` for filesystem-style browsing without an OS mount:

```
stash vfs "find /me -maxdepth 3 -type f"
stash vfs "rg \"database migration\" /me"
stash vfs "cat '/me/README.md' | sed -n '1,80p'"
stash vfs "cat '/me/sessions/_index.jsonl'"
stash search "<query>"
stash whoami --json
```
