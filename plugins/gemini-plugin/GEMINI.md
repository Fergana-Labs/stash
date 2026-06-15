# Stash

You have the `stash` CLI on your PATH. Run `stash --help` to see commands. Use it to read transcripts, pages, and history from your team's shared Stash workspace.

Your activity in this repo is streamed to that workspace, so teammates' agents and humans can see what you're working on.

When the user asks you to upload local files to Stash, use `stash upload <path> --json` and give the user the returned `url`. If you use `stash upload <path> --json` for a raw file upload, give the user the returned `app_url`.

Common reads (all support `--json`):
- `stash sessions search "<query>"` — full-text search across transcripts
- `stash sessions query --limit 20` — recent events
- `stash sessions agents` — who's been active
- `stash files pages --all` — shared pages
