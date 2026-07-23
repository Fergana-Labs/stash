# Stash Plugin for Gemini CLI

Streams Gemini CLI sessions to your Stash.

## Prerequisites

- `stash` CLI installed and signed in (`uv tool install stashai && stash signin`)
- Gemini CLI ≥ the version that shipped `hooks` in `settings.json`

## Install

`stash signin` detects Gemini CLI and wires this plugin automatically
(re-running it refreshes the hooks; `stash settings` can toggle agents later).

The installer merges the `hooks` block from `settings.snippet.json` into
`~/.gemini/settings.json` (preserving your other settings and hooks) and
append the Stash block to `~/.gemini/GEMINI.md`.

Reload with `/hooks reload` inside Gemini CLI, or restart the session.

## What streams

| Gemini event | Stash event |
|---|---|
| `SessionStart` | — (warms cache) |
| `BeforeAgent` | `user_message` |
| `AfterTool` | `tool_use` |
| `AfterAgent` | `assistant_message` + `session_end` |
| `SessionEnd` | — (clears state) |

## Commands

Everything is a plain `stash` CLI subcommand — no Gemini-specific slash commands:

| Command | Description |
|---------|-------------|
| `stash signin` | Interactive setup (auth + hook install) |
| `stash settings` | Interactive settings page (streaming, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

## Known gaps

- `BeforeTool` fires before tool args are final in some tool flavors — we only subscribe to `AfterTool` to avoid noise

## Retrieval

Gemini CLI has shell access. For reads mid-conversation, let the agent
shell out to the `stash` CLI — all commands support `--json`:

```
stash vfs "cat '/me/sessions/_index.jsonl'"
stash search "<query>"
stash whoami --json
```
