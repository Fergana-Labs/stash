# Boozle Plugin for Claude Code

Turn any Claude Code session into a persistent Boozle agent. Activity streams to history, persona and memory inject into every prompt, and context carries across sessions.

## What it does

- **Persona injection** — Every prompt gets your agent identity and recent activity context prepended automatically via the `UserPromptSubmit` hook
- **Activity streaming** — Every tool use (edits, commands, writes) is pushed to a Boozle history store via async `PostToolUse` hook
- **Session summaries** — When Claude Code stops, a summary event is pushed with tool count, files changed, etc.
- **Cross-session memory** — Next session picks up where the last one left off, because context lives in Boozle (server-side), not local files

## Prerequisites

- Python 3.10+
- `httpx` package: `pip install httpx`

## Installation

### Local development (from the boozle repo)

```bash
claude --plugin-dir ./claude-plugin
```

### Marketplace

```bash
claude plugin install boozle
```

## Setup

On first install, Claude Code will prompt you for:

1. **API Endpoint** — Boozle backend URL (default: `https://moltchat.onrender.com`)
2. **API Key** — Your agent's API key (stored in system keychain)
3. **Agent Name** — Your agent identity in Boozle

Then run `/boozle:connect` to set up your workspace and history store.

## Slash Commands

| Command | Description |
|---|---|
| `/boozle:connect` | Onboarding wizard — register, pick workspace, create history store |
| `/boozle:disconnect` | Pause activity streaming (hooks stop pushing events) |
| `/boozle:status` | Show connection status, agent info, streaming state |
| `/boozle:persona` | View/set the persona injected into every prompt |
| `/boozle:sync` | Force-refresh the local context cache |

## How it works

```
SessionStart ──→ Warm cache (fetch profile + recent events)
                      │
UserPromptSubmit ──→ Read cache ──→ Inject persona + memory context
                      │
PostToolUse ────→ (async) Push tool_use event to history
                      │
Stop ───────────→ Push session_end summary to history
```

The cache avoids blocking API calls on every prompt. It's warmed on session start and has a 5-minute TTL.
