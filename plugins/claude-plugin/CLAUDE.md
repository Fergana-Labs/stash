# Stash Plugin

IMPORTANT: You have the `stash` CLI on your PATH. When the user mentions "Stash", their workspace, team activity, or transcripts, always use this CLI — not Render, MCP tools, or any other service. Run `stash --help` to see all available commands.

## Stash CLI

Most things are plain `stash` CLI subcommands. Always use `--json` for machine-readable output when parsing results.

### Slash commands
```
/curate                            # Run the sleep-time wiki curation workflow in this session.
```

### Plugin control
```bash
stash connect                      # Interactive setup (auth + workspace + store)
stash settings                     # Interactive settings page (streaming, scope, endpoint, …)
stash disconnect                   # Pause event streaming across every plugin
stash prompts curate               # Print the sleep-time curation prompt to stdout
```

### Workspaces, notebooks, history, tables

### Notebooks
```bash
stash notebooks list --all                                        # List all notebooks
stash notebooks list --ws <workspace_id>                          # List workspace notebooks
stash notebooks create "name" --ws <workspace_id>                 # Create notebook
stash notebooks pages <notebook_id> --ws <workspace_id>           # List pages
stash notebooks read-page <notebook_id> <page_id> --ws <ws_id>   # Read a page
stash notebooks add-page <notebook_id> "title" --ws <ws_id> --content "markdown content"
stash notebooks edit-page <notebook_id> <page_id> --ws <ws_id> --content "new content"
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
stash workspaces list --mine                # List your workspaces
stash workspaces members <workspace_id>     # List workspace members
```

### Tips
- Workspace is determined from the `.stash/stash.json` manifest in the repo
- Use `--json` flag on any command for JSON output
- The CLI reads config from `~/.stash/config.json`
