# Stash Plugin for Codex CLI

Streams Codex CLI sessions to Stash using Codex's native `hooks` system.

## Prerequisites

- `stash` CLI installed (on PATH) and signed in
- Codex CLI with `features.hooks = true` enabled for hook-based streaming

Streaming is gated globally: it is on whenever you are signed in
(`stash signin`) and haven't stopped streaming (`stash disconnect`). There is
no per-repo manifest.

## Install

Run `stash signin` (or `stash settings`) — it writes `~/.codex/hooks.json`,
merges `config.toml.snippet` into `~/.codex/config.toml`, and upserts
`~/.codex/AGENTS.md`.

For a manual install, copy `hooks.json` to `~/.codex/hooks.json` as-is. Every
hook is the stable command `stash hook run codex <event>`, so the file is
machine-independent and never changes across upgrades.

## Trust

Codex refuses to run new or changed command hooks until you approve them.
After installing (or whenever the hook commands change), restart Codex and
approve the Stash hooks in its hook review (`/hooks`). Nothing streams until
then.

## Auto-update

On session start, if no preference is recorded, the plugin asks (via a
`systemMessage` to the agent) whether Stash may update itself automatically.
Record the choice with `stash hook auto-update on|off`; it is stored as
`codex_auto_update` in `~/.stash/config.json`. Manual upgrades stay available
via `stash upgrade`.

## Commands

Everything is a plain `stash` CLI subcommand — no slash commands or skills:

| Command | Description |
|---------|-------------|
| `stash connect` | Interactive setup (auth + store) |
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
stash vfs "find /me -maxdepth 3 -type f"
stash vfs "rg \"database migration\" /me"
stash vfs "cat '/me/README.md'"
stash vfs "cat '/me/sessions/_index.jsonl'"
stash search "<query>"
stash whoami --json
```
