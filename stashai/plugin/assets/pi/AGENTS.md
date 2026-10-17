# Stash

You have the `stash` CLI on your PATH. Run `stash --help` to see commands. Use it to read transcripts, pages, and history from your Stash.

Your activity in this repo is streamed to your Stash, so your other agents and you can see what you're working on.

## What a Skill is

<!-- stash:skill-model -->
A Skill is a *special folder* — one containing a SKILL.md — holding related artifacts
(pages, files, tables) that shares like any folder and gains a public URL when
published. Use one when you're publishing a *collection* of related things together — a
project writeup with its supporting files, a research thread with its sources, a session
transcript frozen as a page plus the files it produced.

A Skill is **not** a wrapper to slap on every single file you happen to share. One-item Skills
clutter Discover and defeat the model. Pick the right tool:

- Share a single file or a folder/project → `stash upload <path> --json`, hand over `app_url` (no Skill).
- Publishing a curated bundle → `stash upload <path> --skill "<title>" --json`.
- Creating a fresh skill → `stash skills create "<name>" --description "<what it holds>" --public --json`.
- Share a coding session → `stash share` (this one), or `stash share --session "<title>"` for another.

Run `stash prompts agent-guidance` to reprint this rule mid-session.

## Browsing

`stash ls` shows everything Stash can reach as one filesystem — your files, session transcripts, and every connected integration (GitHub, Slack, Gong, Gmail, Drive, Notion, …). When asked what you have access to, run it and show the tree; drill in with `stash ls <source>/<path>`.

Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS. It accepts bash-shaped commands over the virtual Stash tree:
- `stash vfs ls /me`
- `stash vfs "find /me -maxdepth 3 -type f"`
- `stash vfs "rg \"query\" /me"`
- `stash vfs "cat '/me/README.md'"`

## Common reads (all support `--json`)

- `stash search "<query>"` — full-text search across transcripts
- `stash vfs "cat '/me/sessions/_index.jsonl'"` — recent events
- `stash sessions agents` — who's been active
- `stash vfs "find /me -name '*.md'"` — your pages
