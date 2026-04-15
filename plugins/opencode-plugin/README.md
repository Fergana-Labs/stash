# Octopus Plugin for opencode

Streams opencode sessions to an Octopus workspace.

## Prerequisites

- `octopus` CLI installed and logged in
- `octopus config default_workspace <id>` set
- Python 3.10+ and `httpx`
- opencode installed (Bun-based runtime — opencode transpiles TS directly, no build step needed)

## Install

Point your opencode config at `plugin.ts`. The config key is `plugin` (singular):

```jsonc
// ~/.config/opencode/opencode.json (or <project>/opencode.json)
{
  "plugin": ["/absolute/path/to/octopus/plugins/opencode-plugin/plugin.ts"]
}
```

Or drop the plugin into your project's `.opencode/plugin/` directory (note: singular `plugin/`, not `plugins/`).

Restart opencode.

## How it works

`plugin.ts` registers two keyed hooks (`chat.message`, `tool.execute.after`) plus a single `event` dispatcher for bus events. All real logic lives in `plugins/shared/` and is identical to the Claude/Cursor/Gemini/Codex plugins.

| opencode signal | Octopus event |
|---|---|
| `chat.message` (keyed hook) | `user_message` |
| `tool.execute.after` (keyed hook) | `tool_use` |
| bus event `session.created` | — (records session id) |
| bus event `session.deleted` | `session_end` (clears state) |

Ignored on purpose: `session.idle` fires on every turn completion (not session end), `message.updated` streams repeatedly. Capturing final assistant text per turn is a future TODO.

## Known gaps

- No final-assistant-message capture — `session.idle` fires too often to treat as "stop."
- No auto-curation hook — run `octopus curate` on a cron if desired.

## Retrieval

opencode agents have shell access. Point the agent at the `octopus` CLI for reads mid-conversation — all commands support `--json`:

```
octopus history query --ws <id> --limit 20 --json
octopus history search "<query>" --ws <id> --json
octopus whoami --json
octopus workspace list --mine --json
```
