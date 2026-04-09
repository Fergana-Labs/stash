---
name: disconnect
description: Pause Octopus activity streaming. Hooks stop pushing events to history. MCP tools remain available.
---

# Octopus Disconnect

Disable activity streaming to Octopus history.

## Steps

1. Read the state file at `~/.claude/plugins/data/octopus/state.json`
2. Set `streaming_enabled` to `false`
3. Write the updated state back
4. Confirm to the user that activity streaming is paused
5. Note: this does NOT disconnect from Octopus entirely — the persona injection and slash commands still work. Only the PostToolUse and Stop hooks stop pushing events.

To re-enable, the user can run `/octopus:connect` or manually edit the state file.
