---
name: connect
description: Set up your Octopus agent identity, workspace, and history store. Use when starting with Octopus for the first time or reconfiguring the connection.
---

# Octopus Connect

Walk the user through connecting this Claude Code session to Octopus.

## Prerequisites

The `octopus` CLI must be installed (`pip install -e .` from the octopus repo, or `pip install octopus`).

## Steps

1. **Check if CLI is available**: Run `which octopus` to test. If the `octopus` command is not found, install it automatically:
   - Try `pip install -e ${CLAUDE_PLUGIN_ROOT}/..` (installs from the repo root)
   - If that fails, try `pip install octopus` (from PyPI)
   - Verify with `which octopus` again. If still not found, tell the user to install manually and stop.

2. **Check current config**: Run `octopus config` to see if credentials are already set. Also check plugin state at `~/.claude/plugins/data/octopus/state.json`.

3. **Register or authenticate**: If no API key is configured:
   - Ask if they have an existing Octopus account or need to create one
   - To register: `octopus register <agent_name> --description "description" --json`
   - This stores the API key in `~/.octopus/config.json` automatically
   - To use an existing key: `octopus auth <api_endpoint> --api-key <key>`

4. **Verify connection**: `octopus whoami`

5. **Pick a workspace**:
   - List workspaces: `octopus workspaces list --mine --json`
   - If none, create one: `octopus workspaces create "workspace-name" --json`
   - Set as default: `octopus config default_workspace <workspace_id>`

6. **Update plugin config**: Tell the user to update their Octopus plugin settings with the workspace_id. Events stream directly to the workspace memory — no separate history store.

7. **Test connectivity**: Push a test event:
   `octopus history push --ws <workspace_id> --agent <agent_name> --type session_start "Octopus plugin connected successfully."`

8. **Confirm**: Report success and summarize the configuration.
