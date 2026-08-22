# Stash

You have the `stash` CLI on your PATH. Run `stash --help` to see commands. Use it to read transcripts, pages, and history from your Stash.

Your activity in this repo is streamed to your Stash, so your other agents and you can see what you're working on.

## What a Skill is

A **Skill** is a *special folder* — one containing a SKILL.md — holding related artifacts (pages, files, tables) that shares like any folder and gains a public URL when published. Use one when you're publishing a *collection* of related things together — a project writeup with its supporting files, a research thread with its sources, a session transcript plus the files it produced.

A Skill is **not** a wrapper to slap on every single file you happen to share. One-item Skills clutter Discover and defeat the model.

## How to share things

- **One file someone should look at** → `stash upload <path> --json` and hand them the returned `app_url`. No Skill needed.
- **A folder / project into your Stash** → `stash upload <path> --json`. Returns the folder `app_url`. No Skill created by default.
- **A curated bundle as one shareable thing** → `stash upload <path> --skill "<title>" --json`, or `stash skills create "<name>" --public` to start a fresh one. Returns the Skill `url`.
- **A coding session (transcript + touched files)** → `stash share <session_id>`. Sessions are inherently a bundle.

Run `stash prompts agent-guidance` any time you want this guidance reprinted in full.

## Browsing

`stash ls` shows everything Stash can reach as one filesystem — your files, session transcripts, and every connected integration (GitHub, Slack, Gong, Gmail, Drive, Notion, …). When asked what you have access to, run it and show the tree; drill in with `stash ls <source>/<path>`.

Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS. It accepts bash-shaped commands over the virtual Stash tree:
- `stash vfs ls /me`
- `stash vfs "find /me -maxdepth 3 -type f"`
- `stash vfs "rg \"query\" /me"`
- `stash vfs "cat '/me/README.md' | sed -n '1,80p'"`

## Common reads (all support `--json`)

- `stash search "<query>"` — full-text search across transcripts
- `stash vfs "cat '/me/sessions/_index.jsonl'"` — recent events
- `stash sessions agents` — who's been active
- `stash vfs "find /me -name '*.md'"` — your pages
