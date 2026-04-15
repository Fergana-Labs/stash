---
name: status
description: Show Octopus connection status — agent name, workspace, streaming state.
---

# Octopus Status

Display the current Octopus plugin configuration and connection health.

## Steps

1. **Read config**: Run `octopus config` to get CLI config (base_url, default_workspace, default_chat). Output is already JSON-formatted.

2. **Read plugin state** from `~/.claude/plugins/data/octopus/state.json`:
   - `streaming_enabled`
   - `session_id`

3. **Verify connectivity**: `octopus whoami --json`

4. **Check workspace**: If a default workspace is set:
   `octopus workspaces list --mine --json`

5. **Check recent activity**: If a default workspace is set:
   `octopus history query --ws <workspace_id> --limit 1 --json`

6. **Display** a formatted status summary:
   ```
   Octopus Status
   ---
   Agent:      {agent_name}
   Endpoint:   {base_url}
   Workspace:  {workspace_name} ({workspace_id})
   Streaming:  {enabled/disabled}
   Connection: {OK / Error: ...}
   ```
