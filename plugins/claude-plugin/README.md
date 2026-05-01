# Stash Plugin for Claude Code

Turn any Claude Code session into an Stash agent. Every prompt, tool use, and session summary streams to your workspace's shared history.

## Quick Start (5 minutes)

### Step 1: Create an account

Go to [joinstash.ai/login](https://joinstash.ai/login) and register a human account. Save your API key — it's shown only once.

### Step 2: Install the plugin

```bash
claude plugin marketplace add Fergana-Labs/stash
claude plugin install stash@stash-plugins
```

Claude Code will prompt you for three config values:

| Config | Value |
|--------|-------|
| `api_key` | Your API key (from step 1) |
| `tag_name` | A name for this tag (any string) |
| `api_endpoint` | `https://joinstash.ai` (default, usually skip) |

### Step 3: Connect to a workspace

From any shell, run:

```
stash connect
```

This interactive wizard will:
1. Verify your auth
2. Let you pick or create a workspace
3. Save defaults to `~/.stash/config.json`

After this, every session streams directly to that workspace's memory.

### Step 4: You're done

Every Claude Code session now automatically:
- Streams the user's prompts to the workspace history
- Streams tool usage (edits, commands, writes) to the workspace history
- Pushes a session summary when you stop

**This is set-and-forget.** Config persists — new sessions work automatically with no re-configuration.

---

## Team Setup

To collaborate with teammates in a shared workspace:

1. Each person follows Steps 1-2 above (own account, plugin installed)
2. One person creates a workspace at [joinstash.ai/rooms](https://joinstash.ai/rooms)
3. Share the **invite code** (shown on the workspace page) with teammates
4. Each person runs `stash connect` and joins the workspace

Now everyone's activity streams to the same workspace. You can:
- Collaborate on shared notebooks
- Query each other's activity (`stash history query --ws <workspace_id>`)

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `api_endpoint` | `https://joinstash.ai` | Stash backend URL |
| `api_key` | *(required)* | Your API key |
| `tag_name` | *(required)* | Tag name (any string) |
| `workspace_id` | *(optional)* | Set via `stash connect` |
| `auto_curate` | `true` | Spawn `claude -p` headless at session end to curate history into wiki pages. Stored in `~/.stash/config.json`. |

---

## What Happens Each Session

```
SessionStart ──→ Record session ID

UserPromptSubmit ──→ Push user_message event to workspace history

PostToolUse ────→ (async) Push tool_use event to workspace history
                  (Read, Glob, Grep excluded — too noisy)

Stop ───────────→ Push session_end summary (tool count, files changed)

SessionEnd ─────→ Spawn `claude -p` headless with the shared sleep prompt to
                  curate recent history into wiki pages. Gated by `auto_curate`
                  + a 24h cooldown stored in ~/.stash/config.json.
```

### Curation (sleep time compute)

At SessionEnd the plugin shells out to the user's own agent CLI (`claude -p …`)
and hands it a shared curation prompt. The agent reads recent history, merges
it into an organized wiki notebook, and exits. Every installed plugin uses the
same prompt — Codex users get Codex curation, Gemini users get Gemini
curation, and so on.

---

## Commands

Everything is a `stash` CLI subcommand — there are no slash commands.

| Command | Description |
|---------|-------------|
| `stash connect` | Onboarding wizard — pick workspace, create history store |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause activity streaming across every installed plugin |

The plugin also gives Claude access to the rest of the `stash` CLI. Key commands:

```bash
stash history search "database migration" --ws <workspace_id>   # Full-text search events
stash history query --ws <workspace_id> --limit 20              # Recent events
stash history query --all --limit 20                             # Cross-workspace events
stash notebooks list --all                                       # List all notebooks
stash workspaces list --mine                                     # List your workspaces
```

Workspace is determined from the `.stash` manifest in the repo.

---

## Prerequisites

- Python 3.10+
- `httpx` package: `pip install httpx`
