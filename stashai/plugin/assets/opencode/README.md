# Stash Plugin for opencode

Streams opencode sessions to an Stash workspace.

## Prerequisites

- `stash` CLI installed and logged in
- `stash config default_workspace <id>` set
- Python 3.10+ and `httpx`
- opencode installed (Bun-based runtime — opencode transpiles TS directly, no build step needed)

## Install

Point your opencode config at `plugin.ts`. The config key is `plugin` (singular):

```jsonc
// ~/.config/opencode/opencode.json (or <project>/opencode.json)
{
  "plugin": ["/absolute/path/to/stash/plugins/opencode-plugin/plugin.ts"]
}
```

Or drop the plugin into your project's `.opencode/plugin/` directory (note: singular `plugin/`, not `plugins/`).

Restart opencode.

## How it works

`plugin.ts` registers two keyed hooks (`chat.message`, `tool.execute.after`) plus a single `event` dispatcher for bus events. All real logic lives in the `stashai.plugin` Python package (shipped via `pip install stashai`) and is identical to the Claude/Cursor/Gemini/Codex plugins.

| opencode signal | Stash event |
|---|---|
| `chat.message` (keyed hook) | `user_message` |
| `tool.execute.after` (keyed hook) | `tool_use` |
| bus event `session.created` | — (records session id) |
| bus event `session.deleted` | `session_end` (clears state) |

Ignored on purpose: `session.idle` fires on every turn completion (not session end), `message.updated` streams repeatedly. Capturing final assistant text per turn is a future TODO.

## Commands

Everything is a plain `stash` CLI subcommand — no opencode-specific slash commands:

| Command | Description |
|---------|-------------|
| `stash connect` | Interactive setup (auth + workspace + store) |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

When the opencode bus emits `session.deleted` the plugin spawns `opencode run …`
headless with a shared curation prompt. Toggle with `auto_curate` in
`~/.stash/config.json`.

## Known gaps

- No final-assistant-message capture — `session.idle` fires too often to treat as "stop."

## Retrieval

opencode agents have shell access. Point the agent at the `stash` CLI for reads mid-conversation — all commands support `--json`:

```
stash history query --ws <id> --limit 20 --json
stash history search "<query>" --ws <id> --json
stash whoami --json
stash workspace list --mine --json
```
