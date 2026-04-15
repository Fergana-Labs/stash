# Octopus Plugin for Claude Code

Turn any Claude Code session into an Octopus agent. Every prompt, tool use, and session summary streams to your workspace's shared history.

## Quick Start (5 minutes)

### Step 1: Create an account

Go to [getoctopus.com/login](https://getoctopus.com/login) and register a human account. Save your API key — it's shown only once.

### Step 2: Install the plugin

```bash
# From the octopus repo
claude plugin add ./claude-plugin

# Or from the marketplace
claude plugin install octopus
```

Claude Code will prompt you for three config values:

| Config | Value |
|--------|-------|
| `api_key` | Your API key (from step 1) |
| `agent_name` | A name for this agent (any string) |
| `api_endpoint` | `https://getoctopus.com` (default, usually skip) |

### Step 3: Connect to a workspace

Start a Claude Code session and run:

```
/octopus:connect
```

This interactive wizard will:
1. Verify your auth
2. Let you pick or create a workspace

After this, `workspace_id` is saved in your plugin config and every session streams directly to that workspace's memory.

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
2. One person creates a workspace at [getoctopus.com/rooms](https://getoctopus.com/rooms)
3. Share the **invite code** (shown on the workspace page) with teammates
4. Each person runs `/octopus:connect` and joins the workspace

Now everyone's activity streams to the same workspace. You can:
- Collaborate on shared notebooks
- Query each other's activity (`octopus history query --ws <workspace_id>`)

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `api_endpoint` | `https://getoctopus.com` | Octopus backend URL |
| `api_key` | *(required)* | Your API key |
| `agent_name` | *(required)* | Agent name (any string) |
| `workspace_id` | *(optional)* | Set via `/octopus:connect` |
| `auto_curate` | `true` | Run `/octopus:sleep` at session end to re-index history into wiki pages |

---

## What Happens Each Session

```
SessionStart ──→ Record session ID

UserPromptSubmit ──→ Push user_message event to workspace history

PostToolUse ────→ (async) Push tool_use event to workspace history
                  (Read, Glob, Grep excluded — too noisy)

Stop ───────────→ Push session_end summary (tool count, files changed)

SessionEnd ─────→ Optional: spawn `/octopus:sleep` to curate history
                  (gated by auto_curate + 30-min cooldown)
```

---

## Slash Commands

| Command | Description |
|---------|-------------|
| `/octopus:connect` | Onboarding wizard — pick workspace |
| `/octopus:disconnect` | Pause activity streaming |
| `/octopus:status` | Show connection status and config |
| `/octopus:sleep` | Curate workspace history into wiki pages |
| `/octopus:search` | Search across workspace resources |

## CLI Commands

The plugin also gives Claude access to the `octopus` CLI. Key commands:

```bash
octopus history search "database migration" --ws <workspace_id>   # Full-text search events
octopus history query --ws <workspace_id> --limit 20              # Recent events
octopus history query --all --limit 20                             # Cross-workspace events
octopus notebooks list --all                                       # List all notebooks
octopus workspaces list --mine                                     # List your workspaces
```

Set a default workspace to avoid repeating it:
```bash
octopus config default_workspace <id>
```

---

## Prerequisites

- Python 3.10+
- `httpx` package: `pip install httpx`
