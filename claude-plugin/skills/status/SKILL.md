---
name: status
description: Show Boozle connection status — agent identity, workspace, history store, streaming state.
---

# Boozle Status

Display the current Boozle plugin configuration and connection health.

## Steps

1. **Read config**: Run `boozle config --json` to get CLI config (base_url, default_workspace, default_chat, default_store).

2. **Read plugin state** from `~/.claude/plugins/data/boozle/state.json`:
   - `streaming_enabled`
   - `persona`
   - `session_id`

3. **Verify connectivity**: `boozle whoami --json`

4. **Check workspace**: If a default workspace is set:
   `boozle workspaces list --mine --json`

5. **Check history store**: If a default store is set:
   `boozle history query --ws <workspace_id> --store <store_id> --limit 1 --json`

6. **Display** a formatted status summary:
   ```
   Boozle Status
   ---
   Agent:      {agent_name}
   Endpoint:   {base_url}
   Workspace:  {workspace_name} ({workspace_id})
   History:    {store_name} ({store_id})
   Streaming:  {enabled/disabled}
   Persona:    {persona or "(using profile description)"}
   Connection: {OK / Error: ...}
   ```
