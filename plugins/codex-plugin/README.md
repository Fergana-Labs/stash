# Octopus Plugin for Codex CLI

Streams Codex CLI sessions to Octopus. Uses Codex's experimental `hooks`
system with a stable `notify` fallback for older builds.

## Prerequisites

- `octopus` CLI installed and logged in
- `octopus config default_workspace <id>` set
- Python 3.10+ and `httpx`
- Codex CLI with `features.codex_hooks = true` enabled for hook-based streaming

## Install

```bash
cd path/to/octopus/plugins/codex-plugin
export PLUGIN_ROOT=$(pwd)
mkdir -p ~/.codex

# Hooks manifest
envsubst < hooks.json > ~/.codex/hooks.json

# Merge the config.toml snippet (enables hooks + registers notify fallback)
envsubst < config.toml.snippet >> ~/.codex/config.toml
```

## Commands

Everything is a plain `octopus` CLI subcommand — no slash commands or skills:

| Command | Description |
|---------|-------------|
| `octopus connect` | Interactive setup (auth + workspace + store) |
| `octopus status` | Central config, streaming state, last curate |
| `octopus disconnect` | Pause event streaming across every installed plugin |

At session end (Codex `Stop`) the plugin spawns `codex exec …` headless with
a shared curation prompt. Toggle with `auto_curate` in `~/.octopus/config.json`.

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

| Codex event | Octopus event | Notes |
|---|---|---|
| `SessionStart` | — (warms cache) | — |
| `UserPromptSubmit` | `user_message` | — |
| `PostToolUse` | `tool_use` | **Bash only today** — Codex hardcodes `tool_name="Bash"` for every shell call |
| `Stop` | `assistant_message` + `session_end` | — |
| `notify` (fallback) | `assistant_message` + `session_end` | Dedups with Stop — pick one |

## Retrieval

Codex has shell access. For reads mid-conversation, have the agent invoke
the `octopus` CLI — all commands support `--json`:

```
octopus history query --ws <id> --limit 20 --json
octopus history search "<query>" --ws <id> --json
octopus whoami --json
octopus workspace list --mine --json
```
