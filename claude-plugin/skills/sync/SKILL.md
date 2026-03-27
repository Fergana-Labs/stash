---
name: sync
description: Force-refresh the local context cache from Boozle. Use after long gaps between sessions or when context seems stale.
---

# Boozle Sync

Force-refresh the local context cache that the UserPromptSubmit hook uses for persona injection.

## Steps

1. Read config from environment variables (`CLAUDE_PLUGIN_USER_CONFIG_*`)

2. Fetch agent profile:
   `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/users/me`

3. Fetch recent history events (if workspace and history store are configured):
   `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/workspaces/{workspace_id}/memory/{history_store_id}/events?limit=20`

4. Write the results to the cache file at `~/.claude/plugins/data/boozle/context_cache.json` in this format:
   ```json
   {
     "_timestamp": <unix_timestamp>,
     "profile": { ... },
     "recent_events": [ ... ]
   }
   ```

5. Report what was synced: agent name, number of recent events loaded, cache freshness.
