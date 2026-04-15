# Octopus Plugin for opencode

Streams opencode sessions to an Octopus workspace. Richest event model of
the bunch — opencode's plugin API exposes ~25 events and we use 5 of them.

## Prerequisites

- `octopus` CLI installed and logged in (`pip install octopus && octopus login`)
- `octopus config default_workspace <id>` set
- Python 3.10+ and `httpx`
- opencode installed (Node 20+)

## Install

Point your opencode plugins config at `plugin.ts`. Per the opencode docs,
either:

```jsonc
// ~/.config/opencode/config.json
{
  "plugins": ["/absolute/path/to/octopus/plugins/opencode-plugin/plugin.ts"]
}
```

Or drop a symlink into your project's `.opencode/plugins/` directory.

Restart opencode.

## How it works

`plugin.ts` is a thin TypeScript shim — it subscribes to five opencode
events, normalizes each payload to JSON, and pipes it into the matching
Python script via stdin. All real logic lives in `plugins/shared/` and is
identical to the Claude/Cursor/Gemini/Codex plugins.

| opencode event | Octopus event |
|---|---|
| `session.created` | — (warms cache) |
| `message.updated` (user role) | `user_message` |
| `tool.execute.after` | `tool_use` |
| `session.idle` | `assistant_message` + `session_end` |
| `session.deleted` | — (clears state) |

## Known gaps

- No prompt-time context injection (opencode has no analogous protocol). Use
  the MCP server for retrieval or rely on the pre-session cache warm.
- No auto-curation hook — run `octopus curate` on a cron if desired.
