# Stash Plugin for Gemini CLI

Streams Gemini CLI sessions to an Stash workspace.

## Prerequisites

- `stash` CLI installed and logged in
- `.stash/stash.json` manifest present in repo (or ancestor)
- Python 3.10+ and `httpx` (`pip install httpx`)
- Gemini CLI ≥ the version that shipped `hooks` in `settings.json`

## Install

```bash
cd path/to/stash/plugins/gemini-plugin
export PLUGIN_ROOT=$(pwd)

# Merge the snippet into your settings.json.
# If ~/.gemini/settings.json doesn't exist yet:
mkdir -p ~/.gemini
envsubst < settings.snippet.json > ~/.gemini/settings.json

# Agent context — tells Gemini it has the stash CLI available
cat GEMINI.md >> ~/.gemini/GEMINI.md
```

If you already have a `~/.gemini/settings.json`, merge the `hooks` block by
hand (or with `jq`).

Reload with `/hooks reload` inside Gemini CLI, or restart the session.

## What streams

| Gemini event | Stash event |
|---|---|
| `SessionStart` | — (warms cache) |
| `BeforeAgent` | `user_message` |
| `AfterTool` | `tool_use` |
| `AfterAgent` | `assistant_message` + `session_end` |
| `SessionEnd` | — (clears state) |

## Commands

Everything is a plain `stash` CLI subcommand — no Gemini-specific slash commands:

| Command | Description |
|---------|-------------|
| `stash connect` | Interactive setup (auth + workspace + store) |
| `stash settings` | Interactive settings page (streaming, scope, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

At SessionEnd the plugin spawns `gemini -p …` headless with a shared curation
prompt. Toggle with `auto_curate` in `~/.stash/config.json`.

## Known gaps

- `BeforeTool` fires before tool args are final in some tool flavors — we only subscribe to `AfterTool` to avoid noise

## Retrieval

Gemini CLI has shell access. For reads mid-conversation, let the agent
shell out to the `stash` CLI — all commands support `--json`:

```
stash history query --ws <id> --limit 20 --json
stash history search "<query>" --ws <id> --json
stash whoami --json
stash workspace list --mine --json
```
