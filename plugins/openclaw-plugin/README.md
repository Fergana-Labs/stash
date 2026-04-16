# Stash Plugin for Openclaw

Streams Openclaw gateway sessions to a Stash workspace so you can read
history from the `stash` CLI or the Assert review app.

**Openclaw is a self-hosted chat-app gateway**, not an IDE — it bridges
WhatsApp / Telegram / Slack / iMessage / etc. to a coding agent running on
your own machine. This plugin registers against Openclaw's internal hook
system (`command:*`, `message:*`) and streams the gateway-visible slice of
each session to Stash.

Tool-call history (`edit`, `bash`, etc.) is captured by the IDE-side plugin
for whichever agent Openclaw delegates to (Claude Code / Codex / etc.).
Install that plugin too if you want full-fidelity history.

## Layout

```
openclaw-plugin/
├── HOOK.md          # Openclaw hook manifest (frontmatter matches openclaw/openclaw)
├── handler.ts       # Hook entrypoint — exports default HookHandler
├── package.json
├── scripts/         # Python scripts reusing plugins/shared/
│   ├── adapt.py
│   ├── config.py
│   ├── on_session_start.py
│   ├── on_prompt.py
│   ├── on_stop.py
│   └── on_session_end.py
└── README.md
```

`handler.ts` runs inside the Openclaw Node process, filters the events it
cares about, and pipes a flat JSON payload into the matching Python script.
The Python side reuses `plugins/shared/` just like every other agent's plugin.

## Install

See `HOOK.md` for the full install flow. Short version:

```bash
openclaw plugins install github:Fergana-Labs/octopus#plugins/openclaw-plugin
openclaw hooks enable stash
# restart the gateway
```

## Event mapping

| Openclaw event | Stash event |
|---|---|
| `command:new` | `session_start` |
| `message:received` | `user_message` |
| `message:sent` (success=true) | `assistant_message` |
| `command:reset`, `command:stop` | `session_end` |

## Known gaps

- **No `tool_use` stream** — Openclaw's gateway has no tool-call visibility.
  Rely on the delegated agent's own Stash plugin.
- **No prompt injection** — Openclaw forwards raw channel messages; context
  injection is the underlying agent's job.
- **Session IDs are Openclaw `sessionKey`s**, not Stash UUIDs.

## Retrieval

Openclaw routes messages to a coding agent. That agent has shell access, so
point it at the `stash` CLI for reads mid-conversation — all commands support
`--json`:

```
stash history query --ws <id> --limit 20 --json
stash history search "<query>" --ws <id> --json
stash whoami --json
stash workspaces list --mine --json
```
