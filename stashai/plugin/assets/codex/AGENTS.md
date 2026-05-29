# Stash

You have the `stash` CLI on your PATH. Run `stash --help` to see commands. Use it to read transcripts, pages, and history from your team's shared Stash workspace.

Your activity in this repo is streamed to that workspace, so teammates' agents and humans can see what you're working on.

## What a Stash is

A **Stash** is a *named, curated bundle of related artifacts* (pages, files, sessions, tables) with its own access control and an optional public URL. Use one when you're publishing a *collection* of related things together — a project writeup with its supporting files, a research thread with its sources, a session transcript plus the files it produced.

A Stash is **not** a wrapper to slap on every single file you happen to share. One-item Stashes clutter Discover and defeat the model.

## How to share things

- **One file your teammate should look at** → `stash files upload <path> --json` and hand them the returned `app_url`. No Stash needed.
- **A folder / project into the workspace** → `stash upload <path> --json`. Returns the folder `app_url`. No Stash created by default.
- **A curated bundle as one shareable thing** → `stash upload <path> --stash "<title>" --json`, or `stash stashes create "<title>" --items '<json>'` to compose from existing items. Returns the Stash `url`.
- **A coding session (transcript + touched files)** → `stash share <session_id>`. Sessions are inherently a bundle.

Run `stash prompts agent-guidance` any time you want this guidance reprinted in full.

## Browsing

Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS. It accepts bash-shaped commands over the virtual Stash tree:
- `stash vfs ls /`
- `stash vfs "find /workspaces -maxdepth 3 -type f"`
- `stash vfs "rg \"query\" /workspaces"`
- `stash vfs "cat '/workspaces/<workspace>/README.md' | sed -n '1,80p'"`

## Common reads (all support `--json`)

- `stash sessions search "<query>"` — full-text search across transcripts
- `stash sessions query --limit 20` — recent events
- `stash sessions agents` — who's been active
- `stash files pages --all` — shared pages
