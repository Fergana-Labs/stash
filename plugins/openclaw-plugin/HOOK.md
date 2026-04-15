---
name: octopus
description: "Stream Openclaw gateway sessions to an Octopus workspace (persona + history)"
homepage: https://github.com/Fergana-Labs/octopus/tree/main/plugins/openclaw-plugin
metadata:
  {
    "openclaw":
      {
        "emoji": "🐙",
        "events": ["command", "message"],
        "install": [{ "id": "octopus", "kind": "external", "label": "Octopus plugin repo" }],
      },
  }
---

# Octopus Hook for Openclaw

Streams every inbound/outbound gateway message and session boundary to your
Octopus workspace so you (or your teammates) can read the history from the
`octopus` CLI or the Assert review app.

## What it captures

| Openclaw event | Octopus event |
|---|---|
| `command:new` | `session_start` |
| `message:received` | `user_message` (body from the channel) |
| `message:sent` (success=true) | `assistant_message` + `session_end` frame |
| `command:reset`, `command:stop` | `session_end` |

Skipped: `command:stop` with no prior activity, `message:sent` where
`success=false`, audio-only messages prior to transcription.

## Known gaps vs the IDE-side plugins

- **No `tool_use` stream.** Openclaw's gateway has no visibility into tool calls;
  those happen inside the delegated coding agent (Claude Code / Codex / Pi).
  Install the matching Octopus plugin for that agent to get tool-level history.
- **No context injection.** Openclaw routes raw channel messages to the
  underlying agent; persona context is the underlying agent's responsibility.
- **Session IDs use Openclaw's `sessionKey`** (e.g. `agent:main:main`), not an
  Octopus session UUID. They are stable per-agent-per-conversation.

## Requirements

- Openclaw `>= 0.9` (internal hooks API)
- Python 3.10+ on PATH (this hook shells out to Python for the Octopus API client)
- `httpx` installed (`pip install httpx`)
- `octopus` CLI logged in (`pip install octopus && octopus login`)
- `octopus config default_workspace <id>` set

## Install

```bash
openclaw plugins install github:Fergana-Labs/octopus#plugins/openclaw-plugin
openclaw hooks enable octopus
# restart the gateway
```

Or from a local checkout:

```bash
openclaw plugins install ./plugins/openclaw-plugin
openclaw hooks enable octopus
```

## Config

Reads from `~/.octopus/config.json` (populated by `octopus login` +
`octopus config …`). Override with env vars in the gateway's environment:

- `OCTOPUS_OPENCLAW_DATA=<path>` — custom state dir (default `~/.octopus/plugins/openclaw`)
- `OCTOPUS_NOTIFICATIONS_DIR=<path>` — pending escalation notifications

## Disable

```bash
openclaw hooks disable octopus
```

Or via `~/.openclaw/openclaw.json`:

```json
{
  "hooks": {
    "internal": {
      "entries": {
        "octopus": { "enabled": false }
      }
    }
  }
}
```
