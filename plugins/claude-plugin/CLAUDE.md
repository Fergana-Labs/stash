# Stash Plugin

IMPORTANT: You have the `stash` CLI on your PATH. When the user mentions "Stash", their workspace, team activity, or transcripts, always use this CLI. Run `stash --help` to see all available commands.

## What a Skill is

A **Skill** is a *special folder* — one containing a SKILL.md — holding related artifacts (pages, files, tables) that shares like any folder and gains a public URL when published. It is the unit you reach for when you want to publish a *collection* of things together — a project writeup with its supporting files, a research thread with its sources, a session transcript plus the files it produced.

A Skill is **not** a wrapper around every single file you happen to share. One-item Skills clutter Discover and the workspace sidebar, and they defeat the model.

### Decision rule for sharing

| What you want to do | Command | What you give the user |
|---|---|---|
| Share one file with your teammate (internal) | `stash files upload <path> --json` | the returned `app_url` |
| Upload a folder / project into the workspace | `stash upload <path> --json` | the returned `app_url` |
| Publish a curated bundle as one shareable thing | `stash upload <path> --skill "<title>" --json` | the returned `url` |
| Create a fresh skill folder | `stash skills create "<name>" --public --json` | the returned folder |
| Share a coding session (transcript + files) | `stash share <session_id>` | the returned `url` |

The default of `stash upload` is **no Skill** — files land in a workspace folder and you hand back the workspace `app_url`. Add `--skill "<title>"` only when you're deliberately publishing a bundle.

Run `stash prompts agent-guidance` to reprint this rule mid-session.

## Stash CLI

Most things are plain `stash` CLI subcommands. Always use `--json` for machine-readable output when parsing results.

### Everything as a filesystem
`stash ls` renders everything Stash can reach as one tree — workspace files, session transcripts, and every connected integration (GitHub, Slack, Gong, Gmail, Drive, Notion, …). When asked what you have access to, run it and show the tree.
```bash
stash ls                           # The whole company as a filesystem
stash ls gong                      # One integration's contents
stash ls my-repo/docs              # Drill into a directory
stash ls -L 3 --json               # Deeper tree, machine-readable
```

### Virtual filesystem
Use `stash vfs` when you want to browse Stash like a filesystem without mounting anything into the OS. It accepts bash-shaped commands over the virtual Stash tree:
```bash
stash vfs ls /
stash vfs "find /workspaces -maxdepth 3 -type f"
stash vfs "rg \"query\" /workspaces"
stash vfs "cat '/workspaces/<workspace>/README.md' | sed -n '1,80p'"
```

### Plugin control
```bash
stash connect                      # Interactive setup (auth + workspace + store)
stash settings                     # Interactive settings page (streaming, scope, endpoint, …)
stash disconnect                   # Pause event streaming across every plugin
```

### Workspaces, files, history, tables

### Files
```bash
stash files tree --ws <workspace_id>                               # Show folders and pages
stash files pages --ws <workspace_id>                              # List workspace pages
stash files pages --all                                            # List shared pages across workspaces
stash files create-folder "name" --ws <workspace_id>               # Create a folder
stash files add-page "title" --ws <ws_id> --content "markdown content"
stash files read-page <page_id> --ws <ws_id>                       # Read a page
stash files edit-page <page_id> --ws <ws_id> --content "new content"
```

### History (Agent Event Logs)
```bash
stash sessions agents --ws <workspace_id>                              # List distinct agent names
stash sessions push "text" --ws <ws_id> --agent <name> --type <event_type>
stash sessions query --ws <ws_id> --limit 20                           # Query events
stash sessions search "query" --ws <ws_id>                             # Full-text search
stash sessions query --all --limit 20                                  # Cross-workspace events
```

### Tables
```bash
stash tables list --ws <workspace_id>                            # List tables
stash tables search <table_id> "query" --ws <workspace_id>      # Search rows
```

### Workspaces
```bash
stash workspaces list                # List your workspaces
stash workspaces members <workspace_id>     # List workspace members
```

### Tips
- Workspace is determined from the `.stash` manifest in the repo
- Use `--json` flag on any command for JSON output
- The CLI reads config from `~/.stash/config.json`
