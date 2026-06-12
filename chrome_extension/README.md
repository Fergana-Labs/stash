# Stash Chat Sync (Chrome extension)

Automatically saves your ChatGPT (chatgpt.com) and Claude (claude.ai)
conversations into Stash as agent sessions. No buttons: while a
conversation tab is open, the extension snapshots the chat via the site's
own JSON API and uploads it to Stash, replacing the previous snapshot of
the same conversation. Each conversation becomes one Stash session
(`chatgpt-{id}` / `claude-web-{id}`) viewable at `/sessions/{session_id}`.

## How it works

- Content scripts on chatgpt.com and claude.ai poll the open conversation
  every 15s (visible tabs only, plus a flush when you switch away) and
  send a normalized transcript to the background worker.
- The background worker dedupes by content hash, then uploads the
  transcript as JSONL to `POST /api/v1/workspaces/{id}/transcripts` with
  `replace=true`, so re-syncs update the session instead of duplicating it.
- Auth reuses the CLI device flow: the extension opens `/connect-token`,
  you sign in once, and it receives its own revocable `mc_` API key.

## Development

```bash
npm install
npm run build        # or: npm run watch
```

Then load the `chrome_extension/` folder via `chrome://extensions` →
Developer mode → Load unpacked. Point it at a local stack via the popup's
Advanced section (`http://localhost:3456`).

`npm run typecheck` runs tsc.
