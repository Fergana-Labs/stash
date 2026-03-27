---
name: status
description: Show Boozle connection status — agent identity, workspace, history store, streaming state.
---

# Boozle Status

Display the current Boozle plugin configuration and connection health.

## Steps

1. **Read config** from environment variables:
   - `CLAUDE_PLUGIN_USER_CONFIG_api_endpoint`
   - `CLAUDE_PLUGIN_USER_CONFIG_agent_name`
   - `CLAUDE_PLUGIN_USER_CONFIG_workspace_id`
   - `CLAUDE_PLUGIN_USER_CONFIG_history_store_id`

2. **Read state** from `~/.claude/plugins/data/boozle/state.json`:
   - `streaming_enabled`
   - `persona`
   - `session_id`

3. **Verify connectivity**: `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/users/me`

4. **Check workspace**: If workspace_id is set, fetch workspace info:
   `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/workspaces/{workspace_id}`

5. **Check history store**: If history_store_id is set, list events to get a count:
   `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/workspaces/{workspace_id}/memory/{history_store_id}/events?limit=1`

6. **Display** a formatted status summary:
   ```
   Boozle Status
   ─────────────
   Agent:      {agent_name}
   Endpoint:   {api_endpoint}
   Workspace:  {workspace_name} ({workspace_id})
   History:    {store_name} ({history_store_id})
   Streaming:  {enabled/disabled}
   Persona:    {persona or "(using profile description)"}
   Connection: {OK / Error: ...}
   ```
