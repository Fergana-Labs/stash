<!-- stash-context -->
## Stash

This repo uses [Stash](https://joinstash.ai) for shared agent sessions.
Your coding agent has the `stash` CLI on its PATH. Run `stash --help` to see commands.

**Before starting work, use Stash to check for relevant context.** When you need to understand
why something was built a certain way, what's been tried before, or what teammates are working on,
search Stash first — it has the full session record and human decisions across the team.

### What a Skill is

A Skill is a *special folder* — one containing a SKILL.md — holding related artifacts
(pages, files, tables) that shares like any folder and gains a public URL when
published. Use one when you're publishing a *collection* of related things together — a
project writeup with its supporting files, a research thread with its sources, a session
transcript frozen as a page plus the files it produced.

A Skill is **not** a wrapper to slap on every single file you happen to share. One-item Skills
clutter your Skills and defeat the model. Pick the right tool:

- Share a single file or a folder/project → `stash upload <path> --json`, hand over `app_url` (no Skill).
- Publishing a curated bundle → `stash upload <path> --skill "<title>" --json`.
- Creating a fresh skill → `stash skills create "<name>" --public --json`.
- Share a coding session → `stash share` (this one), or `stash share --session "<title>"` for another.

Run `stash prompts agent-guidance` to reprint this rule mid-session.

### Browsing Stash

Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS:
- `stash vfs ls /`
- `stash vfs "find / -maxdepth 3 -type f"`
- `stash vfs "rg 'query' /"`
- `stash vfs "cat '/files/README.md'"`

Common reads:
- `stash search "<query>" --json` — full-text search across files, sessions, and connected sources
- `stash vfs "ls /"` — browse your files, sessions, tables, skills, and connected sources
- `stash sql "SELECT ..."` — query your tables with SQL (tables live in the folder tree; bare name when unique, '"files/<folder>".<name>' otherwise)
- `stash vfs "cat '/sessions/_index.jsonl'"` — recent sessions
- `stash sessions agents` — who's been active

Common writes:
- `stash memory write "<Topic>/<Page>" --content "..."` — fold what you learned into the Memory wiki
- `stash share --title "..."` — share this session as a public Skill
- `stash read <url>` — read a public Skill URL
