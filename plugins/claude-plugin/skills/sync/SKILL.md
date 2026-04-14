---
name: sync
description: Force-refresh the local context cache from Octopus. Use after long gaps between sessions or when context seems stale.
---

# Octopus Sync

Force-refresh the local context cache that the UserPromptSubmit hook uses for context injection.

## Steps

1. Fetch agent profile: `octopus whoami --json`

2. Fetch recent history events (if default workspace and store are configured):
   `octopus history query --all --limit 20 --json`

3. Write the results to the cache file at `~/.claude/plugins/data/octopus/context_cache.json` in this format:
   ```json
   {
     "_timestamp": <unix_timestamp>,
     "profile": { ... },
     "recent_events": [ ... ]
   }
   ```

4. Report what was synced: agent name, number of recent events loaded, cache freshness.
