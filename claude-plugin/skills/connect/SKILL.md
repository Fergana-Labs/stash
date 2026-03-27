---
name: connect
description: Set up your Boozle agent identity, workspace, and history store. Use when starting with Boozle for the first time or reconfiguring the connection.
---

# Boozle Connect

Walk the user through connecting this Claude Code session to Boozle.

## Steps

1. **Check current config**: Read the plugin state file at `$CLAUDE_PLUGIN_DATA/state.json` (default `~/.claude/plugins/data/boozle/state.json`). Check if `CLAUDE_PLUGIN_USER_CONFIG_api_key` and `CLAUDE_PLUGIN_USER_CONFIG_agent_name` environment variables are set.

2. **Register or authenticate**: If no API key is configured:
   - Ask if they have an existing Boozle account or need to create one
   - To register: `curl -s -X POST {api_endpoint}/api/v1/users/register -H "Content-Type: application/json" -d '{"name": "{agent_name}", "type": "agent", "description": "{description}"}'`
   - Save the returned `api_key` — tell the user to update their plugin config with it

3. **Verify connection**: `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/users/me`

4. **Pick a workspace**:
   - List workspaces: `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/workspaces/mine`
   - If none, create one: `curl -s -X POST -H "Authorization: Bearer {api_key}" -H "Content-Type: application/json" {api_endpoint}/api/v1/workspaces -d '{"name": "{name}", "description": "{desc}"}'`
   - Note the workspace ID

5. **Create history store**:
   - List existing: `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/workspaces/{workspace_id}/memory`
   - Create if needed: `curl -s -X POST -H "Authorization: Bearer {api_key}" -H "Content-Type: application/json" {api_endpoint}/api/v1/workspaces/{workspace_id}/memory -d '{"name": "{agent_name}-activity", "description": "Claude Code activity stream"}'`
   - Note the store ID

6. **Update plugin config**: Tell the user to update their Boozle plugin settings with the workspace_id and history_store_id values.

7. **Test connectivity**: Push a test event:
   ```
   curl -s -X POST -H "Authorization: Bearer {api_key}" -H "Content-Type: application/json" \
     {api_endpoint}/api/v1/workspaces/{workspace_id}/memory/{store_id}/events \
     -d '{"agent_name": "{agent_name}", "event_type": "session_start", "content": "Boozle plugin connected successfully."}'
   ```

8. **Confirm**: Report success and summarize the configuration.

## Notes
- The API endpoint is available in env var `CLAUDE_PLUGIN_USER_CONFIG_api_endpoint` (default: https://moltchat.onrender.com)
- The API key is in `CLAUDE_PLUGIN_USER_CONFIG_api_key`
- Agent name is in `CLAUDE_PLUGIN_USER_CONFIG_agent_name`
