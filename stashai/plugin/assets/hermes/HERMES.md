# Stash

You have the `stash` CLI on your PATH. Run `stash --help` to see commands. Use it to read transcripts, pages, and history from your Stash.

Your activity in this repo is streamed to your Stash, so your agents and you can see what you're working on across sessions.

When the user asks you to upload local files to Stash, use `stash upload <path> --json` and give the user the returned `url`. If you use `stash upload <path> --json` for a raw file upload, give the user the returned `app_url`.

`stash upload` always creates a NEW item. To change a page already in Stash, use `stash edit <page_id> --content "..."` (`--append` adds to the end; the page id or its app URL both work) — never re-upload to edit.

Common reads (all support `--json`):
- `stash search "<query>"` — full-text search across transcripts
- `stash vfs "cat '/me/sessions/_index.jsonl'"` — recent events
- `stash sessions agents` — who's been active
- `stash vfs "find /me -name '*.md'"` — your pages
