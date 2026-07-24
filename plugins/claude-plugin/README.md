# Stash Plugin for Claude Code

Turn any Claude Code session into a Stash agent. Every prompt, tool use, assistant message, and artifact streams to your Stash history.

## Quick Start (2 minutes)

```bash
uv tool install stashai
stash signin
```

`stash signin` opens your browser to sign in (or create an account), saves
your credentials to `~/.stash/config.json`, detects Claude Code, and installs
this plugin via the marketplace — no API key to copy anywhere.

To install the plugin by hand instead:

```bash
claude plugin marketplace add Fergana-Labs/stash
claude plugin install stash@stash-plugins
```

The manual path still needs `stash signin` once for auth; the plugin reads
`~/.stash/config.json` when its own config values are unset.

### You're done

Every Claude Code session now automatically:
- Streams the user's prompts to your Stash history
- Streams tool usage (edits, commands, writes) to your Stash history
- Uploads the assistant message, transcript, and artifacts when you stop

**This is set-and-forget.** Config persists — new sessions work automatically with no re-configuration.

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `api_endpoint` | `https://joinstash.ai` | Stash backend URL |
| `api_key` | *(required)* | Your API key |
| `agent_name` | *(required)* | Agent name (any string) |

---

## What Happens Each Session

```
SessionStart ──→ Record session ID

UserPromptSubmit ──→ Push user_message event to your Stash history

PostToolUse ────→ (async) Push tool_use event to your Stash history
                  (Read, Glob, Grep excluded — too noisy)

Stop ───────────→ Push session_end event (tool count, files changed)
```

---

## Commands

Everything is a `stash` CLI subcommand — there are no slash commands.

| Command | Description |
|---------|-------------|
| `stash signin` | Onboarding wizard — auth + hook install |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause activity streaming across every installed plugin |

The plugin also gives Claude access to the rest of the `stash` CLI. Key commands:

```bash
stash vfs "find /me -maxdepth 3 -type f"               # Browse Stash like a filesystem without an OS mount
stash vfs "rg \"database migration\" /me"              # Search the virtual Stash tree
stash vfs "cat '/me/README.md'"
stash search "database migration"                       # Full-text search events
stash vfs "cat '/me/sessions/_index.jsonl'"            # Recent events
stash vfs "find /me -name '*.md'"                      # List all pages
```

---

## Prerequisites

- The `stash` CLI (`uv tool install stashai`) — the plugin's hook scripts run
  under the same Python environment the CLI installs.
