# Stash Desktop

A Tauri app that makes the local-curator setup feel stable and real:

- **Getting set up** — onboarding checklist: signed in to Stash, `stash` CLI
  installed, Claude Code installed, Stash plugin installed. Sign-in uses the
  same browser device-auth flow as `stash signin` and writes the key to
  `~/.stash/config.json`, so the CLI and plugins share it.
- **Health** — backend reachability, connected integrations (with
  needs-reconnect warnings), and per-source sync status.
- **Memory curator** — status of the server-side curator (last run, errors,
  runs this month) with a "Run now" that hits `/api/v1/me/memory/recompute`.
- **Local curator** — runs `claude -p` headlessly on this machine with the
  user's own credentials and MCP connectors, on a schedule, from the tray.
  Off by default; enabled with one switch. Each run maintains the user's
  **personal** knowledge base — the wiki in their personal scope's Memory
  folder — directly (`stash memory write "<Path>"`), pinned to the
  personal scope via `STASH_SCOPE=""` regardless of workspace config. One
  curator per person; nothing is shared with the team. The curation prompt
  is served by the backend (`GET /api/v1/me/local-curator-prompt`, defined
  in `backend/services/prompts.py`) and fetched fresh before every run, so
  prompt changes deploy with the backend — no app release. State (config,
  run history, logs) lives in `~/.stash/curator/`.

  Onboarding note: accounts using the local curator should have the
  server-side Memory curator's nightly run turned off (`stash memory
  --curator off`) — one agent maintains the wiki, not two. On-demand
  recomputes keep working either way.

Closing the window hides to the tray; the scheduler keeps running. "Launch at
login" is a toggle in the app. The interval is measured from the last
*successful* run and an overdue run fires on next launch, so a laptop closed
at the scheduled time curates on wake; a failed run retries after 30 minutes
instead of waiting out the full interval.

## Develop

```sh
npm install
npm run tauri dev
```

## Build

```sh
npm run tauri build
```

All HTTP to the Stash backend happens in Rust (`src-tauri/src/api.rs`), so the
API key never enters the webview. Identity comes from `~/.stash/config.json` —
the same file the CLI owns.
