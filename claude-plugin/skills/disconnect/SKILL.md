---
name: disconnect
description: Pause Boozle activity streaming. Hooks stop pushing events to history. MCP tools remain available.
---

# Boozle Disconnect

Disable activity streaming to Boozle history.

## Steps

1. Read the state file at `~/.claude/plugins/data/boozle/state.json`
2. Set `streaming_enabled` to `false`
3. Write the updated state back
4. Confirm to the user that activity streaming is paused
5. Note: this does NOT disconnect from Boozle entirely — the persona injection and slash commands still work. Only the PostToolUse and Stop hooks stop pushing events.

To re-enable, the user can run `/boozle:connect` or manually edit the state file.
