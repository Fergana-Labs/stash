# Octopus Plugin for Gemini CLI

Streams Gemini CLI sessions to an Octopus workspace and injects persona context
into every prompt.

## Prerequisites

- `octopus` CLI installed and logged in
- `octopus config default_workspace <id>` set
- Python 3.10+ and `httpx` (`pip install httpx`)
- Gemini CLI ≥ the version that shipped `hooks` in `settings.json`

## Install

```bash
cd path/to/octopus/plugins/gemini-plugin
export PLUGIN_ROOT=$(pwd)

# Merge the snippet into your settings.json.
# If ~/.gemini/settings.json doesn't exist yet:
mkdir -p ~/.gemini
envsubst < settings.snippet.json > ~/.gemini/settings.json
```

If you already have a `~/.gemini/settings.json`, merge the `hooks` block by
hand (or with `jq`).

Reload with `/hooks reload` inside Gemini CLI, or restart the session.

## What streams

| Gemini event | Octopus event |
|---|---|
| `SessionStart` | — (warms cache) |
| `BeforeAgent` | `user_message` + context injection |
| `AfterTool` | `tool_use` |
| `AfterAgent` | `assistant_message` + `session_end` |
| `SessionEnd` | — (clears state) |

## Known gaps

- No auto-curation on SessionEnd (Gemini has no headless `-p` flag today)
- No Octopus slash commands — use the `octopus` CLI directly
- `BeforeTool` fires before tool args are final in some tool flavors — we only subscribe to `AfterTool` to avoid noise

## Retrieval

Gemini CLI has shell access. For reads mid-conversation, let the agent
shell out to the `octopus` CLI — all commands support `--json`:

```
octopus history query --ws <id> --limit 20 --json
octopus history search "<query>" --ws <id> --json
octopus whoami --json
octopus workspace list --mine --json
```
