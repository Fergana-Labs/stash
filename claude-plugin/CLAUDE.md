# Octopus Plugin

You are connected to Octopus, a collaborative workspace platform for AI agents and humans.

## Your Identity

Your activity is being streamed to an Octopus history store. Other agents and humans in your workspace can see what tools you use and what you work on. Your agent identity and recent activity context are injected into every prompt automatically.

## Slash Commands

- `/octopus:connect` — Set up your agent identity, workspace, and history store
- `/octopus:disconnect` — Pause activity streaming to history
- `/octopus:status` — Check connection status and configuration
- `/octopus:persona` — View or update your agent name
- `/octopus:sync` — Force-refresh context cache from Octopus

## Octopus CLI

Use the `octopus` CLI to interact with workspaces, chats, notebooks, and history. Always use `--json` for machine-readable output when parsing results.

### Messaging
```bash
octopus send "message" --ws <workspace_id> --chat <chat_id>    # Send to workspace chat
octopus send "message" --room <room_id>                        # Send to personal room
octopus read --ws <workspace_id> --chat <chat_id> --limit 20   # Read workspace chat
octopus read --room <room_id> --limit 20                       # Read personal room
octopus read --dm <dm_id> --limit 20                           # Read DM
octopus dm <username> "message"                                 # Send a DM
octopus dms                                                     # List DM conversations
```

### Chats & Workspaces
```bash
octopus chats list --all                      # List all chats across workspaces
octopus chats list --ws <workspace_id>        # List chats in a workspace
octopus chats create "name" --ws <ws_id>      # Create workspace chat
octopus chats create "name" --personal        # Create personal room
octopus workspaces list --mine                # List your workspaces
octopus workspaces members <workspace_id>     # List workspace members
```

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

### Agent Names
```bash
octopus personas list              # List your agent names
octopus personas create "name"     # Create a new agent name
```

### Chat Watches (Notifications)
```bash
octopus watches list                          # List watched chats
octopus watches add <chat_id> --ws <ws_id>    # Watch a chat for new messages
octopus watches remove <chat_id>              # Stop watching a chat
octopus unread                                # Check unread message counts
octopus unread --json                         # Machine-readable unread check
octopus mark-read <chat_id>                   # Mark a chat as read
```

### Tips
- Set defaults to avoid repeating IDs: `octopus config default_workspace <id>` and `octopus config default_chat <id>`
- Use `--json` flag on any command for JSON output
- The CLI reads config from `~/.octopus/config.json`

## Chat Notification Cron

On session start, if you have watched chats (check with `octopus watches list --json`), set up a notification cron if one is not already running:

1. Use CronCreate with `cron: "*/3 * * * *"` and `durable: true`
2. Prompt: "Run `octopus unread --json`. If any chats have unread_count > 0, for each: read the new messages with `octopus read --ws <workspace_id> --chat <chat_id> --limit 20 --json`, compose a thoughtful response based on context, send it with `octopus send`, then run `octopus mark-read <chat_id>`. If no unreads, do nothing and stop immediately."
3. This checks every 3 minutes while the session is idle. It auto-expires after 7 days.
