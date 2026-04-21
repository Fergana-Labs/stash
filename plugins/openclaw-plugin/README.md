# Stash Extension for Openclaw

Streams every Openclaw session to a Stash workspace so you can read
history from the `stash` CLI or the Assert review app.

This extension hooks into Openclaw's **plugin-hook** system
(`session_start`, `before_message_write`, `session_end`) rather than the
channel-centric internal hooks. That means it captures every turn
regardless of transport — telegram, webchat, Control UI direct chat,
subagents — from the canonical agent runtime itself.

## Layout

```
openclaw-plugin/
├── package.json        # openclaw.extensions entry
├── index.ts            # plugin entry — calls api.on(...) for plugin hooks
├── scripts/            # Python scripts reusing stashai.plugin
│   ├── adapt.py
│   ├── config.py
│   ├── on_session_start.py
│   ├── on_prompt.py
│   ├── on_stop.py
│   └── on_session_end.py
└── README.md
```

`index.ts` runs inside the Openclaw Node process. On each hook it
normalizes the event to a flat JSON payload and pipes it into the matching
Python script. The Python side imports from `stashai.plugin` (shipped via
`pip install stashai`) just like every other agent's plugin.

## Install

```bash
# Prereqs (one-time)
pip install stashai httpx
stash connect
# Ensure .stash/stash.json manifest exists in your repo

# Install the extension
openclaw plugins install github:Fergana-Labs/stash#plugins/openclaw-plugin
# or from a local checkout:
openclaw plugins install ./plugins/openclaw-plugin

# Restart the gateway so the extension loads
openclaw gateway restart
```

If `python3` on the gateway's PATH doesn't have `stashai` installed (e.g.
you installed the CLI via uv), point the extension at the right interpreter:

```bash
# One-line LaunchAgent tweak on macOS
/usr/libexec/PlistBuddy -c 'Add :EnvironmentVariables:STASH_PYTHON string /path/to/python-with-stashai' ~/Library/LaunchAgents/ai.openclaw.gateway.plist
launchctl unload ~/Library/LaunchAgents/ai.openclaw.gateway.plist && launchctl load ~/Library/LaunchAgents/ai.openclaw.gateway.plist
```

## Event mapping

| Openclaw plugin hook | Stash event |
|---|---|
| `session_start` | `session_start` |
| `before_message_write` (role=user) | `user_message` |
| `before_message_write` (role=assistant) | `assistant_message` |
| `session_end` | `session_end` |

`toolResult` messages are skipped — the delegated coding agent's own Stash
plugin captures tool history at higher fidelity.

## Config

Reads from `~/.stash/config.json` (populated by `stash connect` + `stash
config …`). Overrides:

- `STASH_OPENCLAW_DATA=<path>` — custom state dir (default `~/.stash/plugins/openclaw`)
- `STASH_PYTHON=<path>` — Python interpreter to spawn (default `python3`)

## Retrieval

Openclaw routes messages to a coding agent. That agent has shell access,
so point it at the `stash` CLI for reads mid-conversation — all commands
support `--json`:

```
stash history query --ws <id> --limit 20 --json
stash history search "<query>" --ws <id> --json
stash whoami --json
stash workspaces list --mine --json
```
