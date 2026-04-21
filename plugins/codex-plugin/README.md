# Stash Plugin for Codex CLI

Streams Codex CLI sessions to Stash. Uses Codex's experimental `hooks`
system with a stable `notify` fallback for older builds.

## Prerequisites

- `stash` CLI installed and logged in
- `.stash/stash.json` manifest present in repo (or ancestor)
- Python 3.10+ and `httpx`
- Codex CLI with `features.codex_hooks = true` enabled for hook-based streaming

## Install

```bash
cd path/to/stash/plugins/codex-plugin
export PLUGIN_ROOT=$(pwd)
mkdir -p ~/.codex

# Hooks manifest
envsubst < hooks.json > ~/.codex/hooks.json

# Merge the config.toml snippet (enables hooks + registers notify fallback)
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

At session end (Codex `Stop`) the plugin spawns `codex exec …` headless with
a shared curation prompt. Toggle with `auto_curate` in `~/.stash/config.json`.

## Launching: use the `stash` profile

`config.toml.snippet` registers a `[profiles.stash]` block. Launch Codex with
it so stash CLI reads don't hit the sandbox's network block or per-command
approval prompts:

```bash
codex --profile stash
```

The profile sets `sandbox_mode = "workspace-write"` with `network_access =
true` (so `stash history …` can reach `api.stash.ac`) and
`approval_policy = "on-failure"` (so successful reads don't prompt; failures
still do). Run plain `codex` — without the flag — if you want Codex's default
approval behavior.

## ⚠️ Known gaps

1. **Bash-only tool hooks.** Codex's `PostToolUse` today only fires for Bash.
   Edit/read/write won't stream until OpenAI expands hook coverage. The
   `on_stop.py` session summary captures turn-level stats even without
   per-tool hooks.
2. **Windows.** Codex hook support is disabled on Windows in current builds.
3. **No SessionEnd event.** We clear state + trigger curation in `Stop` instead.

## Fallback: the `notify` path

If you're on a Codex build where `codex_hooks` isn't available, the
`notify` command in `config.toml` fires at every turn end with a JSON
payload on stdin. `on_notify.py` handles this case.

**Pick ONE of hooks or notify — enabling both double-fires every turn.**
The `config.toml.snippet` has two mutually-exclusive variants.

## What streams

| Codex event | Stash event | Notes |
|---|---|---|
| `SessionStart` | — (warms cache) | — |
| `UserPromptSubmit` | `user_message` | — |
| `PostToolUse` | `tool_use` | **Bash only today** — Codex hardcodes `tool_name="Bash"` for every shell call |
| `Stop` | `assistant_message` + transcript upload | Transcript uploaded in background with 60s cooldown |
| `notify` (fallback) | `assistant_message` | Dedups with Stop — pick one |

## Retrieval

Codex has shell access. For reads mid-conversation, have the agent invoke
the `stash` CLI — all commands support `--json`:

```
stash history query --ws <id> --limit 20 --json
stash history search "<query>" --ws <id> --json
stash whoami --json
stash workspace list --mine --json
```
