# Stash Plugin for Hermes Agent

Streams Hermes Agent (NousResearch `hermes-agent`) sessions to your Stash via
Hermes shell hooks.

## Prerequisites

- `stash` CLI installed and signed in (`uv tool install stashai && stash signin`)
- Hermes Agent ≥ the version that shipped shell hooks in `config.yaml`
  (see hermes-agent.nousresearch.com/docs/user-guide/features/hooks)

## Install

`stash signin` detects Hermes (the `hermes` binary or `~/.hermes/`) and wires
this plugin automatically (re-running it refreshes the hooks; `stash settings`
can toggle agents later).

The installer writes the `hooks` entries from `config.snippet.yaml` into
`~/.hermes/config.yaml` inside a `# stash-plugin:begin` / `# stash-plugin:end`
marker block, preserving everything else in the file. If your config already
has its own top-level `hooks:` block the installer refuses (duplicate YAML keys
would silently drop one of the blocks) — add the snippet entries to your
existing block by hand instead.

### Approve the hooks (required)

Hermes asks for one-time approval per `(event, command)` pair the first time a
hook fires; approvals persist in `~/.hermes/shell-hooks-allowlist.json`.

- Interactive sessions: approve the five stash hooks when prompted, or run
  `hermes hooks list` to review them first.
- Non-interactive / gateway sessions: pre-approve with `HERMES_ACCEPT_HOOKS=1`,
  `hermes --accept-hooks chat`, or `hooks_auto_accept: true` in config.yaml.
- `hermes hooks doctor` diagnoses hooks that silently stopped firing.

## What streams

| Hermes event | Stash event |
|---|---|
| `on_session_start` | — (creates the session record) |
| `pre_llm_call` | `user_message` (fires once per user turn) |
| `post_tool_call` | `tool_use` |
| `post_llm_call` | `assistant_message` (once per turn, after the tool loop) |
| `on_session_end` | `session_end` + transcript finalize |

Hermes exposes no transcript path, so the session page is materialized from
the streamed events. Hook stdout must be valid JSON for Hermes, so the scripts
always answer `{}` and send any warnings to stderr (Hermes logs).

## Agent context

Hermes has no global context file (only project-level `HERMES.md`/`AGENTS.md`
and the `SOUL.md` personality file, which we never touch). To teach the agent
about the `stash` CLI, copy the block in `HERMES.md` into your project's
`HERMES.md` or `AGENTS.md`.

## Commands

Everything is a plain `stash` CLI subcommand — no Hermes-specific commands:

| Command | Description |
|---------|-------------|
| `stash signin` | Interactive setup (auth + hook install) |
| `stash settings` | Interactive settings page (streaming, endpoint, …) |
| `stash disconnect` | Pause event streaming across every installed plugin |

## Retrieval

Hermes has terminal access. For reads mid-conversation, let the agent shell
out to the `stash` CLI — all commands support `--json`:

```
stash vfs "cat '/me/sessions/_index.jsonl'"
stash search "<query>"
stash whoami --json
```
