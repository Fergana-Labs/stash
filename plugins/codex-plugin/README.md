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

## ⚠️ Known gaps

1. **Bash-only tool hooks.** Codex's `PostToolUse` today only fires for Bash.
   Edit/read/write won't stream until OpenAI expands hook coverage. The
   `on_stop.py` session summary captures turn-level stats even without
   per-tool hooks.
2. **Windows.** Codex hook support is disabled on Windows in current builds.
3. **No SessionEnd event.** We clear state in `Stop` instead.

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
| `UserPromptSubmit` | `user_message` + injection | — |
| `PostToolUse` | `tool_use` | **Bash only today** |
| `Stop` | `assistant_message` + `session_end` | — |
| `notify` (fallback) | `assistant_message` + `session_end` | Dedups with Stop |
