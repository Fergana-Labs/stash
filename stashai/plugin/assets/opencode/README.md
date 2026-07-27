# Stash Plugin for opencode

Streams opencode sessions to your Stash.

## Prerequisites

- `stash` CLI installed (on PATH) and signed in
- opencode installed (Bun-based runtime — opencode transpiles TS directly, no build step needed)

Streaming is gated globally: it is on whenever you are signed in
(`stash signin`) and haven't stopped streaming (`stash disconnect`).

## Install

Point your opencode config at `plugin.ts`. The config key is `plugin` (singular):

```jsonc
// ~/.config/opencode/opencode.json (or <project>/opencode.json)
{
  "plugin": ["/absolute/path/to/stash/plugins/opencode-plugin/plugin.ts"]
}
```

Or drop the plugin into your project's `.opencode/plugin/` directory (note: singular `plugin/`, not `plugins/`).

Also drop `AGENTS.md` beside your opencode config so the agent knows the
`stash` CLI is available:

```bash
cat AGENTS.md >> ~/.config/opencode/AGENTS.md
```

Restart opencode.

## How it works

`plugin.ts` registers two keyed hooks (`chat.message`, `tool.execute.after`) plus a single `event` dispatcher for bus events. Each handler pipes its payload into `stash hook run opencode <event>`, which runs the hook scripts shipped inside the `stashai` package under the package's own Python — identical to the Claude/Gemini/Codex plugins.

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
| `stash connect` | Interactive setup (auth + store) |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

## Known gaps

- No final-assistant-message capture — `session.idle` fires too often to treat as "stop."

## Retrieval

opencode agents have shell access. Point the agent at the `stash` CLI for reads mid-conversation. Use `stash vfs` for filesystem-style browsing without an OS mount:

```
stash vfs "find /me -maxdepth 3 -type f"
stash vfs "rg \"database migration\" /me"
stash vfs "cat '/me/README.md'"
stash vfs "cat '/me/sessions/_index.jsonl'"
stash search "<query>"
stash whoami --json
```
