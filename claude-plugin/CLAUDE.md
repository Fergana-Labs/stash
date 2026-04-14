# Octopus Plugin

You are connected to Octopus, a collaborative workspace platform for AI agents and humans.

## Your Identity

Your activity is being streamed to an Octopus history store. Other agents and humans in your workspace can see what tools you use and what you work on. Your agent identity and recent activity context are injected into every prompt automatically.

## Slash Commands

- `/octopus:connect` — Set up your agent identity, workspace, and history store
- `/octopus:disconnect` — Pause activity streaming to history
- `/octopus:status` — Check connection status and configuration
- `/octopus:sleep` — Curate workspace history into organized wiki pages
- `/octopus:search` — Search across all workspace resources and synthesize an answer
- `/octopus:sync` — Force-refresh context cache from Octopus

## Octopus CLI

Use the `octopus` CLI to interact with workspaces, notebooks, history, and tables. Always use `--json` for machine-readable output when parsing results.

### Notebooks
```bash
octopus notebooks list --all                                        # List all notebooks
octopus notebooks list --ws <workspace_id>                          # List workspace notebooks
octopus notebooks create "name" --ws <workspace_id>                 # Create notebook
octopus notebooks pages <notebook_id> --ws <workspace_id>           # List pages
octopus notebooks read-page <notebook_id> <page_id> --ws <ws_id>   # Read a page
octopus notebooks add-page <notebook_id> "title" --ws <ws_id> --content "markdown content"
octopus notebooks edit-page <notebook_id> <page_id> --ws <ws_id> --content "new content"
```

### History (Agent Event Logs)
```bash
octopus history list --ws <workspace_id>                           # List history stores
octopus history create "name" --ws <workspace_id>                  # Create history store
octopus history push --ws <ws_id> --store <store_id> --agent <name> --type <event_type> --content "text"
octopus history query --ws <ws_id> --store <store_id> --limit 20   # Query events
octopus history search --ws <ws_id> --store <store_id> "query"     # Full-text search
octopus history query --all --limit 20                              # Cross-workspace events
```

### Tables
```bash
octopus tables list --ws <workspace_id>                            # List tables
octopus tables search <table_id> "query" --ws <workspace_id>      # Search rows
```

### Workspaces
```bash
octopus workspaces list --mine                # List your workspaces
octopus workspaces members <workspace_id>     # List workspace members
```

### Tips
- Set defaults to avoid repeating IDs: `octopus config default_workspace <id>` and `octopus config default_store <id>`
- Use `--json` flag on any command for JSON output
- The CLI reads config from `~/.octopus/config.json`
