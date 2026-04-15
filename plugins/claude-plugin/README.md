# Octopus Plugin for Claude Code

Turn any Claude Code session into a persistent Octopus agent. Activity streams to history, memory injects into every prompt, and context carries across sessions.

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

After this, `workspace_id` is saved in your plugin config.

### Step 4: You're done

Every Claude Code session now automatically:
- Streams the user's prompt to the workspace history
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

---

## What Happens Each Session

```
SessionStart ──→ Record session ID

UserPromptSubmit ──→ Push user_message event to history store

PostToolUse ────→ (async) Push tool_use event to history store
                  (Read, Glob, Grep excluded — too noisy)

Stop ───────────→ Push session_end summary (tool count, files changed)
```

---

## Slash Commands

| Command | Description |
|---------|-------------|
| `/octopus:connect` | Onboarding wizard — pick workspace, create history store |
| `/octopus:disconnect` | Pause activity streaming |
| `/octopus:status` | Show connection status and config |

## CLI Commands

The plugin also gives Claude access to the `octopus` CLI. Key commands:

```bash
octopus send "message" --ws <workspace_id> --chat <chat_id>   # Send to chat
octopus read --ws <workspace_id> --chat <chat_id>             # Read chat
octopus history search "database migration"                    # Full-text search events
octopus history query --ws <workspace_id>                      # List recent events
octopus notebooks list --all                                   # List all notebooks
```

Set defaults to avoid repeating IDs:
```bash
octopus config default_workspace <id>
octopus config default_chat <id>
```

---

## Prerequisites

- Python 3.10+
- `httpx` package: `pip install httpx`
