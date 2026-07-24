# Stash Plugin

IMPORTANT: You have the `stash` CLI on your PATH. When the user mentions "Stash", their Stash, their activity, or transcripts, always use this CLI. Run `stash --help` to see all available commands.

## What a Skill is

A **Skill** is a *special folder* — one containing a SKILL.md — holding related artifacts (pages, files, tables) that shares like any folder and gains a public URL when published. It is the unit you reach for when you want to publish a *collection* of things together — a project writeup with its supporting files, a research thread with its sources, a session transcript plus the files it produced.

A Skill is **not** a wrapper around every single file you happen to share. One-item Skills clutter Discover and your Stash sidebar, and they defeat the model.

### Decision rule for sharing

| What you want to do | Command | What you give the user |
|---|---|---|
| Share one file (publicly) | `stash upload <path> --json` | the returned `app_url` |
| Upload a folder / project into your Stash | `stash upload <path> --json` | the returned `app_url` |
| Publish a curated bundle as one shareable thing | `stash upload <path> --skill "<title>" --json` | the returned `url` |
| Create a fresh skill folder | `stash skills create "<name>" --public --json` | the returned folder |
| Share a coding session (transcript + files) | `stash share <session_id>` | the returned `url` |
| Use a public Skill in this agent | `stash skills install <slug>` | the installed `~/.claude/skills` path |
| Sync your Stash skills with local agent skills | `stash skills sync` | runs automatically at session start; two-way |

The default of `stash upload` is **no Skill** — files land in a folder in your Stash and you hand back the `app_url`. Add `--skill "<title>"` only when you're deliberately publishing a bundle.

Run `stash prompts agent-guidance` to reprint this rule mid-session.

## Stash CLI

Most things are plain `stash` CLI subcommands. Always use `--json` for machine-readable output when parsing results.

### Everything as a filesystem
`stash ls` renders everything Stash can reach as one tree — your files, session transcripts, and every connected integration (GitHub, Slack, Gong, Gmail, Drive, Notion, …). When asked what you have access to, run it and show the tree.
```bash
stash ls                           # Everything as a filesystem
stash ls gong                      # One integration's contents
stash ls my-repo/docs              # Drill into a directory
stash ls -L 3 --json               # Deeper tree, machine-readable
```

### Virtual filesystem
Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS. It accepts bash-shaped commands over the virtual Stash tree:
```bash
stash vfs ls /
stash vfs "find /me -maxdepth 3 -type f"
stash vfs "rg \"query\" /me"
stash vfs "cat '/me/README.md'"
```

### Plugin control
```bash
stash signin                       # Interactive setup (auth + hook install)
stash settings                     # Interactive settings page (streaming, scope, endpoint, …)
stash disconnect                   # Pause event streaming across every plugin
```

### Files, history, tables

### Files
```bash
stash vfs "tree /me/files"                          # Show folders and pages
stash vfs "ls /me/files"                            # List your pages
stash vfs "find /me -name '*.md'"                   # List your pages
stash files create-folder "name"                    # Create a folder
stash files add-page "title" --content "markdown content"
stash vfs "cat '/me/files/<page>.md'"               # Read a page
stash files edit-page <page_id> --content "new content"
```

### History (Agent Event Logs)
```bash
stash sessions agents                                  # List distinct agent names
stash sessions push "text" --agent <name> --type <event_type>
stash vfs "cat '/me/sessions/_index.jsonl'"            # Query events
stash search "query"                                   # Full-text search
```

### Tables
```bash
stash vfs "cat '/me/tables/_index.jsonl'"   # List tables
stash tables search <table_id> "query"      # Search rows
```

### Tips
- Use `--json` flag on any command for JSON output
- The CLI reads config from `~/.stash/config.json`
</content>
</invoke>
