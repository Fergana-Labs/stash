# Stash

You have the `stash` CLI on your PATH. Run `stash --help` to see commands. Use it to read transcripts, pages, and history from your team's shared Stash workspace.

Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS. It accepts bash-shaped commands over the virtual Stash tree:
- `stash vfs ls /`
- `stash vfs "find /workspaces -maxdepth 3 -type f"`
- `stash vfs "rg \"query\" /workspaces"`
- `stash vfs "cat '/workspaces/<workspace>/README.md' | sed -n '1,80p'"`

Your activity in this repo is streamed to that workspace, so teammates' agents and humans can see what you're working on.

Common reads (all support `--json`):
- `stash history search "<query>"` — full-text search across transcripts
- `stash history query --limit 20` — recent events
- `stash history agents` — who's been active
- `stash pages --all` — shared pages
