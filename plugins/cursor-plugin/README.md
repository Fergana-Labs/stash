# Octopus Plugin for Cursor

Streams Cursor sessions to an Octopus workspace. Mirrors the Claude Code
plugin's event coverage, minus auto-curation (Cursor has no headless
entry point) and prompt-time context injection (Cursor's `beforeSubmitPrompt`
protocol has no context-injection key).

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
- `OCTOPUS_NOTIFICATIONS_DIR=<path>` — pending escalation notifications

## What streams

| Cursor event | Octopus event | Content |
|---|---|---|
| `sessionStart` | — (warms cache only) | — |
| `beforeSubmitPrompt` | `user_message` | User's prompt text |
| `postToolUse` | `tool_use` | Tool name, tool_input, tool_output preview |
| `afterAgentResponse` | `assistant_message` | Final model text for the turn |
| `stop` | `session_end` | Tool-count summary |
| `sessionEnd` | — (clears session state) | — |

## Known gaps vs Claude plugin

- No auto-curation on SessionEnd (no `cursor -p` equivalent)
- No slash commands (`/octopus:connect` etc.) — use the `octopus` CLI directly
- No prompt-time context injection — Cursor's `beforeSubmitPrompt` protocol has no context-injection key

## Retrieval

Cursor's agent has shell access, so for reads mid-conversation just let it
shell out to the `octopus` CLI. All commands support `--json`:

```
octopus history query --ws <id> --limit 20 --json
octopus history search "<query>" --ws <id> --json
octopus whoami --json
octopus workspace list --mine --json
```
