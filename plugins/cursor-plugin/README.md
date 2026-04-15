# Octopus Plugin for Cursor

Streams Cursor sessions to an Octopus workspace. Mirrors the Claude Code
plugin's event coverage minus auto-curation (Cursor has no headless entry
point).

## Prerequisites

- `octopus` CLI installed and logged in (`pip install octopus && octopus login`)
- `octopus config default_workspace <id>` set
- Python 3.10+ on PATH
- `httpx` installed (`pip install httpx`)

## Install

```bash
cd path/to/octopus/plugins/cursor-plugin

# Symlink hooks.json into Cursor with PLUGIN_ROOT baked in.
export PLUGIN_ROOT=$(pwd)
mkdir -p ~/.cursor
envsubst < hooks.json > ~/.cursor/hooks.json
```

Or, for per-project use, drop `hooks.json` into `<project>/.cursor/hooks.json`
with `${PLUGIN_ROOT}` replaced by the absolute path.

## Verify

```
# In Cursor, open a new chat and send any message.
# Then from a shell:
octopus history query --limit 5
```

You should see a `user_message` event with the prompt you just sent.

## Config

Reads from `~/.octopus/config.json` (populated by `octopus login` +
`octopus config …`). No Cursor-specific config surface.

Override with env vars (set in Cursor's environment):
- `OCTOPUS_CURSOR_DATA=<path>` — custom state dir (default `~/.octopus/plugins/cursor`)

## What streams

| Cursor event | Octopus event | Content |
|---|---|---|
| `sessionStart` | — (records session id) | — |
| `beforeSubmitPrompt` | `user_message` | User's prompt text |
| `postToolUse` | `tool_use` | Tool name, tool_input, tool_output preview |
| `afterAgentResponse` | `assistant_message` | Final model text for the turn |
| `stop` | `session_end` | Tool-count summary |
| `sessionEnd` | — (clears session state) | — |

## Commands

Everything is a plain `octopus` CLI subcommand — no Cursor-specific slash commands:

| Command | Description |
|---------|-------------|
| `octopus connect` | Interactive setup (auth + workspace + store) |
| `octopus status` | Central config, streaming state, last curate |
| `octopus disconnect` | Pause event streaming across every installed plugin |

At SessionEnd the plugin spawns `cursor-agent -p …` headless with a shared
curation prompt. Because `cursor-agent -p` has open hang reports, the spawn
helper kills the subprocess after 10 minutes. Toggle with `auto_curate` in
`~/.octopus/config.json`; Cursor curation may still be experimental depending
on your upstream `cursor-agent` build.

## Known gaps vs Claude plugin

- Cursor curation is best-effort — `cursor-agent -p` can hang; the helper
  enforces a 10-minute kill-on-overrun
- No prompt-time context injection — Cursor's `beforeSubmitPrompt` protocol
  has no context-injection key

## Retrieval

Cursor's agent has shell access, so for reads mid-conversation just let it
shell out to the `octopus` CLI. All commands support `--json`:

```
octopus history query --ws <id> --limit 20 --json
octopus history search "<query>" --ws <id> --json
octopus whoami --json
octopus workspace list --mine --json
```
