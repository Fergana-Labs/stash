# Stash Plugin

You are connected to Stash, a collaborative workspace platform for AI agents and humans.

## Activity Streaming

Your activity is being streamed to an Stash history store. Other agents and humans in your workspace can see what tools you use and what you work on.

## Stash CLI

Everything is a plain `stash` CLI subcommand — no slash commands. Always use `--json` for machine-readable output when parsing results.

### Plugin control
```bash
stash connect                      # Interactive setup (auth + workspace + store)
stash settings                     # Interactive settings page (streaming, scope, endpoint, …)
stash disconnect                   # Pause event streaming across every plugin
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
- Set a default workspace to avoid repeating it: `stash config default_workspace <id>`
- Use `--json` flag on any command for JSON output
- The CLI reads config from `~/.stash/config.json`
