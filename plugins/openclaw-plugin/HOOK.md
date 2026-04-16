---
name: stash
description: "Stream Openclaw gateway sessions to a Stash workspace"
homepage: https://github.com/Fergana-Labs/octopus/tree/main/plugins/openclaw-plugin
metadata:
  {
    "openclaw":
      {
        "emoji": "🐙",
        "events": ["command", "message"],
        "install": [{ "id": "stash", "kind": "external", "label": "Stash plugin repo" }],
      },
  }
---

# Stash Hook for Openclaw

Streams every inbound/outbound gateway message and session boundary to your
Stash workspace so you (or your teammates) can read the history from the
`stash` CLI or the Assert review app.

## What it captures

| Openclaw event | Stash event |
|---|---|
| `command:new` | `session_start` |
| `message:received` | `user_message` (body from the channel) |
| `message:sent` (success=true) | `assistant_message` |
| `command:reset`, `command:stop` | `session_end` |

Skipped: `message:sent` where `success=false`, audio-only messages prior to
transcription.

## Known gaps vs the IDE-side plugins

- **No `tool_use` stream.** Openclaw's gateway has no visibility into tool
  calls; those happen inside the delegated coding agent (Claude Code / Codex
  / etc.). Install the matching Stash plugin for that agent to get
  tool-level history.
- **No context injection.** Openclaw routes raw channel messages to the
  underlying agent; context injection is the underlying agent's job.
- **Session IDs use Openclaw's `sessionKey`** (e.g. `agent:main:main`), not
  a Stash session UUID. They are stable per-agent-per-conversation.

## Requirements

- Openclaw `>= 0.9` (internal hooks API)
- Python 3.10+ on PATH (this hook shells out to Python for the Stash API client)
- `httpx` installed (`pip install httpx`)
- `stash` CLI logged in (`pip install stash-cli && stash connect`)
- `stash config default_workspace <id>` set

## Install

```bash
openclaw plugins install github:Fergana-Labs/octopus#plugins/openclaw-plugin
openclaw hooks enable stash
# restart the gateway
```

Or from a local checkout:

```bash
openclaw plugins install ./plugins/openclaw-plugin
openclaw hooks enable stash
```

## Config

Reads from `~/.stash/config.json` (populated by `stash connect` + `stash
config …`). Override with env vars in the gateway's environment:

- `STASH_OPENCLAW_DATA=<path>` — custom state dir (default `~/.stash/plugins/openclaw`)
- `STASH_PYTHON=<path>` — Python interpreter to spawn (default `python3`)

## Disable

```bash
openclaw hooks disable stash
```

Or via `~/.openclaw/openclaw.json`:

```json
{
  "hooks": {
    "internal": {
      "entries": {
        "stash": { "enabled": false }
      }
    }
  }
}
```
