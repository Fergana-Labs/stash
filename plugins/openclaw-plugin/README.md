# Octopus Plugin for Openclaw

Streams Openclaw sessions to an Octopus workspace and injects persona context
into every prompt. Mirrors the Cursor plugin feature for feature.

## Prerequisites

- `octopus` CLI installed and logged in (`pip install octopus && octopus login`)
- `octopus config default_workspace <id>` set
- Python 3.10+ on PATH
- `httpx` installed (`pip install httpx`)
- Openclaw `>= 0.9` (hooks API landed in the 2026-03 release)

## Install

```bash
cd path/to/octopus/plugins/openclaw-plugin

# Symlink hooks.json into Openclaw with PLUGIN_ROOT baked in.
export PLUGIN_ROOT=$(pwd)
mkdir -p ~/.openclaw
envsubst < hooks.json > ~/.openclaw/hooks.json
```

Or, for per-project use, drop `hooks.json` into `<project>/.openclaw/hooks.json`
with `${PLUGIN_ROOT}` replaced by the absolute path.

## Verify

```
# In Openclaw, open a new session and send any message.
# Then from a shell:
octopus history query --limit 5
```

You should see a `user_message` event with the prompt you just sent.

## Config

Reads from `~/.octopus/config.json` (populated by `octopus login` +
`octopus config …`). No Openclaw-specific config surface.

Override with env vars (set in Openclaw's environment):
- `OCTOPUS_INJECT_CONTEXT=false` — disable prompt injection
- `OCTOPUS_OPENCLAW_DATA=<path>` — custom state dir (default `~/.octopus/plugins/openclaw`)
- `OCTOPUS_NOTIFICATIONS_DIR=<path>` — pending escalation notifications

## What streams

| Openclaw event | Octopus event | Content |
|---|---|---|
| `session.start` | — (warms cache only) | — |
| `prompt.submit` | `user_message` | User's prompt text |
| `tool.after` | `tool_use` | Tool name, args, response preview |
| `turn.end` | `assistant_message` + `session_end` | Last model message + tool-count summary |
| `session.end` | — (clears session state) | — |

## Known gaps vs Claude plugin

- No auto-curation on session.end (no headless `openclaw -p` equivalent yet)
- No slash commands (`/octopus:connect` etc.) — use the `octopus` CLI directly
- Prompt injection uses Openclaw's `contextInject` stdout protocol — verify your Openclaw version supports it
