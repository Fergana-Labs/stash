# Stash Plugin for Cursor

Streams Cursor sessions to your Stash. Mirrors the Claude Code
plugin's event coverage.

## Prerequisites

- `stash` CLI installed (on PATH) and signed in (`uv tool install stashai && stash signin`)

Streaming is gated globally: it is on whenever you are signed in
(`stash signin`) and haven't stopped streaming (`stash disconnect`).

## Install

`stash signin` detects Cursor and merges the hooks into `~/.cursor/hooks.json`
automatically. For a manual install, copy `hooks.json` there as-is — every
hook is the stable command `stash hook run cursor <event>`, so the file is
machine-independent and never changes across upgrades.

For agent context (so Cursor knows the `stash` CLI is available), Cursor
only auto-loads `.mdc` rules from project-level `.cursor/rules/` — there
is no global file location for user rules. Run `stash init` inside a repo
and the installer will drop a `.cursor/rules/stash.mdc` into that repo.
Commit it so teammates' Cursor agents pick it up too.

Or, for per-project use, drop `hooks.json` into `<project>/.cursor/hooks.json`
as-is.

## Verify

```
# In Cursor, open a new chat and send any message.
# Then from a shell:
stash vfs "cat '/me/sessions/_index.jsonl'"
```

You should see a `user_message` event with the prompt you just sent.

## Config

Reads from `~/.stash/config.json` (populated by `stash signin`; change it later with `stash settings`). No Cursor-specific config surface.

Override with env vars (set in Cursor's environment):
- `STASH_CURSOR_DATA=<path>` — custom state dir (default `~/.stash/plugins/cursor`)

## What streams

| Cursor event | Stash event | Content |
|---|---|---|
| `sessionStart` | — (records session id) | — |
| `beforeSubmitPrompt` | `user_message` | User's prompt text |
| `postToolUse` | `tool_use` | Tool name, tool_input, tool_output preview |
| `afterAgentResponse` | `assistant_message` | Final model text for the turn |
| `stop` | `session_end` | Tool count and files changed |
| `sessionEnd` | — (clears session state) | — |

## Commands

Everything is a plain `stash` CLI subcommand — no Cursor-specific slash commands:

| Command | Description |
|---------|-------------|
| `stash connect` | Interactive setup (auth + store) |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

## Known gaps vs Claude plugin

- No prompt-time context injection — Cursor's `beforeSubmitPrompt` protocol
  has no context-injection key

## Retrieval

Cursor's agent has shell access, so for reads mid-conversation just let it
shell out to the `stash` CLI. Use `stash vfs` for filesystem-style browsing without an OS mount:

```
stash vfs "find /me -maxdepth 3 -type f"
stash vfs "rg \"database migration\" /me"
stash vfs "cat '/me/README.md'"
stash vfs "cat '/me/sessions/_index.jsonl'"
stash search "<query>"
stash whoami --json
```
