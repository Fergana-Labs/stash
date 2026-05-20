# Stash Plugin for Cursor

Streams Cursor sessions to an Stash workspace. Mirrors the Claude Code
plugin's event coverage.

## Prerequisites

- `stash` CLI installed and logged in (`pip install stashai && stash login`)
- `.stash` manifest present in repo (or ancestor)
- Python 3.10+ on PATH
- `httpx` installed (`pip install httpx`)

## Install

```bash
cd path/to/stash/plugins/cursor-plugin

# Symlink hooks.json into Cursor with PLUGIN_ROOT baked in.
export PLUGIN_ROOT=$(pwd)
mkdir -p ~/.cursor
envsubst < hooks.json > ~/.cursor/hooks.json
```

For agent context (so Cursor knows the `stash` CLI is available), Cursor
only auto-loads `.mdc` rules from project-level `.cursor/rules/` — there
is no global file location for user rules. Run `stash init` inside a repo
and the installer will drop a `.cursor/rules/stash.mdc` into that repo.
Commit it so teammates' Cursor agents pick it up too.

Or, for per-project use, drop `hooks.json` into `<project>/.cursor/hooks.json`
with `${PLUGIN_ROOT}` replaced by the absolute path.

## Verify

```
# In Cursor, open a new chat and send any message.
# Then from a shell:
stash history query --limit 5
```

You should see a `user_message` event with the prompt you just sent.

## Config

Reads from `~/.stash/config.json` (populated by `stash login` +
`stash config …`). No Cursor-specific config surface.

Override with env vars (set in Cursor's environment):
- `STASH_CURSOR_DATA=<path>` — custom state dir (default `~/.stash/plugins/cursor`)

## What streams

| Cursor event | Stash event | Content |
|---|---|---|
| `sessionStart` | — (records session id) | — |
| `beforeSubmitPrompt` | `user_message` | User's prompt text |
| `postToolUse` | `tool_use` | Tool name, tool_input, tool_output preview |
| `afterAgentResponse` | `assistant_message` | Final model text for the turn |
| `stop` | `session_end` | Tool count and files changed |
| `sessionEnd` | — (clears session state) | — |

## Commands

Everything is a plain `stash` CLI subcommand — no Cursor-specific slash commands:

| Command | Description |
|---------|-------------|
| `stash connect` | Interactive setup (auth + workspace + store) |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

## Known gaps vs Claude plugin

- No prompt-time context injection — Cursor's `beforeSubmitPrompt` protocol
  has no context-injection key

## Retrieval

Cursor's agent has shell access, so for reads mid-conversation just let it
shell out to the `stash` CLI. All commands support `--json`:

```
stash history query --ws <id> --limit 20 --json
stash history search "<query>" --ws <id> --json
stash whoami --json
stash workspaces list --json
```
