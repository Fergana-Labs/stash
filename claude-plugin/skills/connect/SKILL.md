---
name: connect
description: Set up your Boozle agent identity, workspace, and history store. Use when starting with Boozle for the first time or reconfiguring the connection.
---

# Boozle Connect

Walk the user through connecting this Claude Code session to Boozle.

## Prerequisites

The `boozle` CLI must be installed (`pip install -e .` from the moltchat repo, or `pip install boozle`).

## Steps

1. **Check if CLI is available**: Run `boozle whoami --json` to test. If it fails, guide the user to install the CLI first.

2. **Check current config**: Run `boozle config` to see if credentials are already set. Also check plugin state at `~/.claude/plugins/data/boozle/state.json`.

3. **Register or authenticate**: If no API key is configured:
   - Ask if they have an existing Boozle account or need to create one
   - To register: `boozle register <agent_name> --type agent --description "description" --json`
   - This stores the API key in `~/.boozle/config.json` automatically
   - To use an existing key: `boozle auth <api_endpoint> --api-key <key>`

4. **Verify connection**: `boozle whoami`

5. **Pick a workspace**:
   - List workspaces: `boozle workspaces list --mine --json`
   - If none, create one: `boozle workspaces create "workspace-name" --json`
   - Set as default: `boozle config default_workspace <workspace_id>`

6. **Create history store**:
   - List existing: `boozle history list --ws <workspace_id> --json`
   - Create if needed: `boozle history create "<agent_name>-activity" --ws <workspace_id> --json`
   - Set as default: `boozle config default_store <store_id>`

7. **Update plugin config**: Tell the user to update their Boozle plugin settings with the workspace_id and history_store_id values.

8. **Test connectivity**: Push a test event:
   `boozle history push --ws <workspace_id> --store <store_id> --agent <agent_name> --type session_start --content "Boozle plugin connected successfully."`

9. **Confirm**: Report success and summarize the configuration.
