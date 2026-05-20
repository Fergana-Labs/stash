# Stash Plugin

IMPORTANT: You have the `stash` CLI on your PATH. When the user mentions "Stash", their workspace, team activity, or transcripts, always use this CLI. Run `stash --help` to see all available commands.

## Stash CLI

Most things are plain `stash` CLI subcommands. Always use `--json` for machine-readable output when parsing results.

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
stash pages --ws <workspace_id>                              # List workspace pages
stash pages --all                                            # List shared pages across workspaces
stash files create-folder "name" --ws <workspace_id>               # Create a folder
stash files add-page "title" --ws <ws_id> --content "markdown content"
stash files read-page <page_id> --ws <ws_id>                       # Read a page
stash files edit-page <page_id> --ws <ws_id> --content "new content"
```

### History (Agent Event Logs)
```bash
stash history agents --ws <workspace_id>                              # List distinct agent names
stash history push "text" --ws <ws_id> --agent <name> --type <event_type>
stash history query --ws <ws_id> --limit 20                           # Query events
stash history search "query" --ws <ws_id>                             # Full-text search
stash history query --all --limit 20                                  # Cross-workspace events
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
