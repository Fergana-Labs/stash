# Stash Plugin for Codex CLI

Streams Codex CLI sessions to Stash using Codex's native `hooks` system.

## Prerequisites

- `stash` CLI installed and logged in
- `.stash` manifest present in repo (or ancestor)
- Python 3.10+ and `httpx`
- Codex CLI with `features.hooks = true` enabled for hook-based streaming

## Install

```bash
cd path/to/stash/plugins/codex-plugin
export PLUGIN_ROOT=$(pwd)
mkdir -p ~/.codex

# Hooks manifest
envsubst < hooks.json > ~/.codex/hooks.json

# Merge the config.toml snippet (enables hooks)
envsubst < config.toml.snippet >> ~/.codex/config.toml

# Agent context — tells Codex it has the stash CLI available
cat AGENTS.md >> ~/.codex/AGENTS.md
```

## Commands

Everything is a plain `stash` CLI subcommand — no slash commands or skills:

| Command | Description |
|---------|-------------|
| `stash connect` | Interactive setup (auth + workspace + store) |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

## Launching: use the `stash` profile

`config.toml.snippet` registers a `[profiles.stash]` block. Launch Codex with
it so stash CLI reads don't hit the sandbox's network block or per-command
approval prompts:

```bash
codex --profile stash
```

The profile sets `sandbox_mode = "workspace-write"` with `network_access =
true` (so `stash sessions …` can reach `api.joinstash.ai`) and
`approval_policy = "on-failure"` (so successful reads don't prompt; failures
still do). Run plain `codex` — without the flag — if you want Codex's default
approval behavior.

## ⚠️ Known gaps

1. **Bash-only tool hooks.** Codex's `PostToolUse` today only fires for Bash.
   Edit/read/write won't stream until OpenAI expands hook coverage. The
   `on_stop.py` captures turn-level stats even without
   per-tool hooks.
2. **Windows.** Codex hook support is disabled on Windows in current builds.
3. **No SessionEnd event.** Codex only exposes `Stop`, so the plugin uploads the assistant message and transcript there.

## What streams

| Codex event | Stash event | Notes |
|---|---|---|
| `SessionStart` | — (warms cache) | — |
| `UserPromptSubmit` | `user_message` | — |
| `PostToolUse` | `tool_use` | **Bash only today** — Codex hardcodes `tool_name="Bash"` for every shell call |
| `Stop` | `assistant_message` + transcript upload | Transcript uploaded in background with 60s cooldown |

## Retrieval

Codex has shell access. For reads mid-conversation, have the agent invoke
the `stash` CLI. Use `stash vfs` for filesystem-style browsing without an OS mount:

```
stash vfs "find /workspaces -maxdepth 3 -type f"
stash vfs "rg \"database migration\" /workspaces"
stash vfs "cat '/workspaces/<workspace>/README.md' | sed -n '1,80p'"
stash sessions query --ws <id> --limit 20 --json
stash sessions search "<query>" --ws <id> --json
stash whoami --json
```
