# Stash Plugin

You have the `stash` CLI on your PATH. Run `stash --help` to see commands. Use it to read transcripts, notebooks, and history from your team's shared Stash workspace.

Your activity in this repo is also streamed to that workspace, so teammates' agents and humans can see what you're working on.

## Stash CLI

Most things are plain `stash` CLI subcommands. Always use `--json` for machine-readable output when parsing results.

### Slash commands
```
/curate                            # Run the sleep-time wiki curation workflow in this session.
```

### Plugin control
```bash
stash connect                      # Interactive first-time setup (auth + workspace + config)
stash settings                     # Interactive settings page (streaming, scope, endpoint, …)
stash enable                       # Re-enable streaming for this repo
stash disable                      # Pause streaming for this repo (config stays intact)
stash disconnect                   # Sign out and clear config (next `stash connect` re-onboards)
```

### History (Agent Event Logs)
```bash
stash history agents --ws <workspace_id>                                 # List distinct agent names
stash history push "text" --ws <ws_id> --agent <name> --type <type>      # Push an event
stash history push "text" --attach ./file.pdf                            # Push with file attachment
stash history query --ws <ws_id> --limit 20                              # Query events
stash history query --all --limit 20                                     # Cross-workspace events
stash history search "query" --ws <ws_id>                                # Full-text search
stash history transcript <session_id> --ws <ws_id>                       # Fetch session transcript
stash history transcript <session_id> --save ./out.jsonl                 # Save transcript to file
```

### Notebooks
```bash
stash notebooks list --all                                        # List all notebooks (cross-workspace)
stash notebooks list --ws <workspace_id>                          # List workspace notebooks
stash notebooks create "name" --ws <workspace_id>                 # Create notebook
stash notebooks create "name" --personal                          # Create personal notebook
stash notebooks pages <notebook_id> --ws <workspace_id>           # List pages
stash notebooks read-page <notebook_id> <page_id> --ws <ws_id>   # Read a page
stash notebooks add-page <notebook_id> "title" --ws <ws_id> --content "markdown"
stash notebooks add-page <notebook_id> "title" --attach ./img.png # Add page with file attachment
stash notebooks edit-page <notebook_id> <page_id> --ws <ws_id> --content "new content"
stash notebooks edit-page <notebook_id> <page_id> --name "New Title" # Rename a page
```

### Tables
```bash
stash tables list --ws <workspace_id>                             # List workspace tables
stash tables list --all                                           # Cross-workspace
stash tables list --personal                                      # Personal tables
stash tables create "name" --ws <ws_id> --columns '[{"name":"Col","type":"text"}]'
stash tables schema <table_id> --ws <ws_id>                       # Show column schema
stash tables rows <table_id> --ws <ws_id> --limit 50              # Read rows
stash tables rows <table_id> --sort "Name" --order desc           # Sort rows
stash tables rows <table_id> --filter '[{"column_id":"Name","op":"eq","value":"Alice"}]'
stash tables insert <table_id> '{"Name":"Alice"}' --ws <ws_id>   # Insert a row
stash tables import <table_id> -f data.csv --ws <ws_id>           # Bulk import CSV/JSON
stash tables update <table_id> --name "New Name" --ws <ws_id>     # Rename table
stash tables update-row <table_id> <row_id> '{"Status":"done"}'   # Update a row
stash tables delete-row <table_id> <row_id> --ws <ws_id>          # Delete a row
stash tables add-column <table_id> "Col" --type text --ws <ws_id> # Add a column
stash tables delete-column <table_id> <col_id> --ws <ws_id>       # Delete a column
stash tables count <table_id> --ws <ws_id>                        # Count rows
stash tables export <table_id> -f out.csv --ws <ws_id>            # Export as CSV
stash tables delete <table_id> -y --ws <ws_id>                    # Delete table and all data
```

### Files
```bash
stash files upload ./report.pdf --ws <workspace_id>               # Upload to workspace
stash files upload ./photo.png                                    # Upload to personal files
stash files list --ws <workspace_id>                              # List workspace files
stash files list                                                  # List personal files
stash files text <file_id> --ws <workspace_id>                    # Get extracted text (PDF, OCR)
stash files rm <file_id>                                          # Delete a file
```

### Workspaces
```bash
stash workspaces list --mine                                      # List your workspaces
stash workspaces create "name"                                    # Create a workspace
stash workspaces info <workspace_id>                              # Show workspace details
stash workspaces members <workspace_id>                           # List members
stash workspaces join <invite_code>                               # Join via invite code
stash workspaces use <workspace_id_or_name>                       # Set default workspace
stash workspaces use <name> --scope project                       # Set default for this repo only
```

### Invites
```bash
stash invite --ws <workspace_id>                                  # Create a magic-link invite
stash invite --ws <ws_id> --uses 5 --days 30                      # Multi-use, 30-day TTL
stash invite list --ws <workspace_id>                             # List active invite tokens
stash invite revoke <token_id> --ws <workspace_id>                # Revoke an invite
```

### Keys
```bash
stash keys list                                                   # List your API keys
stash keys revoke <key_id>                                        # Revoke an API key
```

### Tips
- Workspace is determined from the `.stash/stash.json` manifest in the repo
- Use `--json` flag on any command for JSON output
- The CLI reads config from `~/.stash/config.json`; project overrides go in `.stash/config.json`
