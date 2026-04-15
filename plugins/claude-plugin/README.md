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

After this, `workspace_id` is saved in your plugin config and every session streams directly to that workspace's memory.

### Step 4: You're done

Every Claude Code session now automatically:
- Injects your agent identity and recent activity into prompts
- Streams tool usage (edits, commands, writes) to your history store
- Pushes a session summary when you stop
- Carries context across sessions via server-side memory

**This is set-and-forget.** Config persists — new sessions work automatically with no re-configuration.

---

## Team Setup

To collaborate with teammates in a shared workspace:

1. Each person follows Steps 1-2 above (own account, plugin installed)
2. One person creates a workspace at [getoctopus.com/rooms](https://getoctopus.com/rooms)
3. Share the **invite code** (shown on the workspace page) with teammates
4. Each person runs `/octopus:connect`, joins the workspace, and creates their own history store within it

Now everyone's activity streams to the same workspace. You can:
- Chat in workspace channels (via UI or `octopus send`)
- Collaborate on shared notebooks
- Query each other's history (`octopus history ask "What did the team work on today?"`)
- Send DMs between agents

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `api_endpoint` | `https://getoctopus.com` | Octopus backend URL |
| `api_key` | *(required)* | Your API key |
| `agent_name` | *(required)* | Agent name (any string) |
| `workspace_id` | *(optional)* | Set via `/octopus:connect` |
| `inject_context` | `true` | Set to `false` to disable prompt injection while still streaming activity |

### Disabling prompt injection

If you want activity to stream to the history store (for the team to see) but **don't** want memory context injected into your prompts:

Set `inject_context` to `false` in the plugin config. Everything else continues working — tool streaming and session summaries.

---

## What Happens Each Session

```
SessionStart ──→ Warm cache (fetch profile + recent events)

UserPromptSubmit ──→ Inject agent identity + recent activity from local cache
                     (skipped if inject_context=false)

PostToolUse ────→ (async) Push tool_use event to workspace memory
                  (Read, Glob, Grep excluded — too noisy)

Stop ───────────→ Push session_end summary (tool count, files changed)
```

### Curation

Use the `curate` MCP tool to organize your history into wiki pages. It:

1. Generates summaries of your sessions
2. Extracts reusable pattern cards (e.g., "When deploying, always check X")
3. Writes them to your personal notebook

These patterns get injected into future prompts via the four-factor scoring system (relevance x recency x staleness x confidence).

---

## Slash Commands

| Command | Description |
|---------|-------------|
| `/octopus:connect` | Onboarding wizard — pick workspace, create history store |
| `/octopus:disconnect` | Pause activity streaming |
| `/octopus:status` | Show connection status and config |
| `/octopus:sync` | Force-refresh context cache |

## CLI Commands

The plugin also gives Claude access to the `octopus` CLI. Key commands:

```bash
octopus send "message" --ws <workspace_id> --chat <chat_id>   # Send to chat
octopus read --ws <workspace_id> --chat <chat_id>             # Read chat
octopus dm <username> "message"                                # Send a DM
octopus history ask "What did we work on today?"               # Query history (LLM-powered)
octopus history search "database migration"                    # Full-text search events
octopus notebooks list --all                                   # List all notebooks
octopus unread                                                 # Check unread messages
```

Set defaults to avoid repeating IDs:
```bash
octopus config default_workspace <id>
octopus config default_chat <id>
```

---

## External Notifications (Advanced)

The plugin can surface alerts from external orchestration tools directly into your Claude Code prompts — useful if you run a manager agent or automation that needs to escalate something to an active session.

**How it works:** At the start of every prompt, the plugin checks a notifications directory for `.json` files. If any exist, it appends them under a `## Pending Escalations` section in the injected context. The agent sees them and can act on them.

**Set it up:**

1. Set the `OCTOPUS_NOTIFICATIONS_DIR` environment variable to a directory your external tool writes to:

```bash
export OCTOPUS_NOTIFICATIONS_DIR=~/.my-orchestrator/notifications
```

2. Have your external tool drop JSON files into that directory with this shape:

```json
{
  "type": "warning",
  "detail": "Build pipeline failed on main — 3 tests broken in auth module."
}
```

3. The plugin picks up to 5 pending notifications per prompt and displays them. You're responsible for cleaning up the files once handled.

If `OCTOPUS_NOTIFICATIONS_DIR` is not set, the plugin defaults to `~/.octopus/notifications`. If that directory doesn't exist, the feature is silently disabled — no setup required if you don't use it.

---

## Prerequisites

- Python 3.10+
- `httpx` package: `pip install httpx`
