# Octopus Plugin for Cursor

Streams Cursor sessions to an Octopus workspace and injects persona context
into every prompt. Mirrors the Claude Code plugin feature for feature,
minus auto-curation (Cursor has no headless entry point).

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
- `OCTOPUS_INJECT_CONTEXT=false` — disable prompt injection
- `OCTOPUS_CURSOR_DATA=<path>` — custom state dir (default `~/.octopus/plugins/cursor`)
- `OCTOPUS_NOTIFICATIONS_DIR=<path>` — pending escalation notifications

## What streams

| Cursor event | Octopus event | Content |
|---|---|---|
| `sessionStart` | — (warms cache only) | — |
| `beforeSubmitPrompt` | `user_message` | User's prompt text |
| `postToolUse` | `tool_use` | Tool name, args, response preview |
| `stop` | `assistant_message` + `session_end` | Last model message + tool-count summary |
| `sessionEnd` | — (clears session state) | — |

## Known gaps vs Claude plugin

- No auto-curation on SessionEnd (no `cursor -p` equivalent)
- No slash commands (`/octopus:connect` etc.) — use the `octopus` CLI directly
- Prompt injection uses Cursor's `injected_context` stdout protocol — verify your Cursor version supports it
