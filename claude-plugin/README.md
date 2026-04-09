# Octopus Plugin for Claude Code

Turn any Claude Code session into a persistent Octopus agent. Activity streams to history, persona and memory inject into every prompt, and context carries across sessions.

## Quick Start (5 minutes)

### Step 1: Create an account

Go to [getoctopus.com/login](https://getoctopus.com/login) and register a human account. Save your API key — it's shown only once.

### Step 2: Create a persona

Your persona is your AI identity in Octopus — it's what Claude Code uses to authenticate.

Go to [getoctopus.com/personas](https://getoctopus.com/personas) → **Create Persona**. Give it a name and description. Save the persona's API key.

> **Why a persona?** Your human account owns the persona. The persona has its own API key, personal notebook, and personal history store — all auto-provisioned. Multiple team members can each have their own persona in a shared workspace.

### Step 3: Install the plugin

```bash
# From the octopus repo
claude plugin add ./claude-plugin

# Or from the marketplace
claude plugin install octopus
```

Claude Code will prompt you for three config values:

| Config | Value |
|--------|-------|
| `api_key` | Your **persona's** API key (from step 2) |
| `agent_name` | Your persona's username |
| `api_endpoint` | `https://getoctopus.com` (default, usually skip) |

### Step 4: Connect to a workspace

Start a Claude Code session and run:

```
/octopus:connect
```

This interactive wizard will:
1. Verify your auth
2. Let you pick or create a workspace
3. Set up a history store for activity streaming

After this, `workspace_id` and `history_store_id` are saved in your plugin config.

### Step 5: You're done

Every Claude Code session now automatically:
- Injects your persona identity and recent activity into prompts
- Streams tool usage (edits, commands, writes) to your history store
- Pushes a session summary when you stop
- Carries context across sessions via server-side memory

**This is set-and-forget.** Config persists — new sessions work automatically with no re-configuration.

---

## Team Setup

To collaborate with teammates in a shared workspace:

1. Each person follows Steps 1-3 above (own account, own persona)
2. One person creates a workspace at [getoctopus.com/rooms](https://getoctopus.com/rooms)
3. Share the **invite code** (shown on the workspace page) with teammates
4. Each person runs `/octopus:connect`, joins the workspace, and creates their own history store within it

Now everyone's activity streams to the same workspace. You can:
- Chat in workspace channels (via UI or `octopus send`)
- Collaborate on shared notebooks
- Query each other's history (`octopus history ask "What did the team work on today?"`)
- Send DMs between personas

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `api_endpoint` | `https://getoctopus.com` | Octopus backend URL |
| `api_key` | *(required)* | Persona API key |
| `agent_name` | *(required)* | Persona username |
| `workspace_id` | *(optional)* | Set via `/octopus:connect` |
| `history_store_id` | *(optional)* | Set via `/octopus:connect` |
| `inject_context` | `true` | Set to `false` to disable prompt injection while still streaming activity |

### Disabling prompt injection

If you want activity to stream to the history store (for the team to see, for the sleep agent to curate) but **don't** want memory context injected into your prompts:

Set `inject_context` to `false` in the plugin config. Everything else continues working — tool streaming, session summaries, sleep curation.

---

## What Happens Each Session

```
SessionStart ──→ Warm cache (fetch profile + recent events)

UserPromptSubmit ──→ Call injection API ──→ Inject persona + scored memory context
                     (skipped if inject_context=false)

PostToolUse ────→ (async) Push tool_use event to history store
                  (Read, Glob, Grep excluded — too noisy)

Stop ───────────→ Push session_end summary (tool count, files changed)
```

### Background: Sleep Agent

Every ~60 minutes, the server-side sleep agent checks your persona's history for new events. If there are any, it:

1. Generates monologue summaries of your sessions
2. Extracts reusable pattern cards (e.g., "When deploying, always check X")
3. Writes them to your persona's personal notebook
4. Scores which injected patterns led to successful outcomes

These patterns get injected into future prompts via the four-factor scoring system (relevance × recency × staleness × confidence).

---

## Slash Commands

| Command | Description |
|---------|-------------|
| `/octopus:connect` | Onboarding wizard — pick workspace, create history store |
| `/octopus:disconnect` | Pause activity streaming |
| `/octopus:status` | Show connection status and config |
| `/octopus:persona` | View/set persona description |
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
octopus personas list                                          # List your personas
octopus unread                                                 # Check unread messages
```

Set defaults to avoid repeating IDs:
```bash
octopus config default_workspace <id>
octopus config default_chat <id>
octopus config default_store <id>
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
