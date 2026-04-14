---
name: persona
description: View or set the agent name that gets injected into every prompt. Use to customize how this Claude Code session identifies itself.
---

# Octopus Agent Name

Manage the agent name injected into every prompt via the UserPromptSubmit hook.

## Usage

**`/octopus:persona`** — Show the current agent name

**`/octopus:persona set <text>`** — Set a custom agent name override

**`/octopus:persona clear`** — Clear the override, revert to Octopus profile description

## Steps

### View (no arguments or $ARGUMENTS is empty)
1. Read state from `~/.claude/plugins/data/octopus/state.json`
2. Read the `persona` field
3. If empty, fetch the agent profile: `octopus whoami --json`
4. Show the current agent name source (local override vs profile description)

### Set ($ARGUMENTS starts with "set")
1. Extract the agent name text after "set "
2. Read current state from `~/.claude/plugins/data/octopus/state.json`
3. Update the `persona` field with the new text
4. Write state back
5. Confirm the agent name has been updated

### Clear ($ARGUMENTS is "clear")
1. Read current state
2. Set `persona` to empty string
3. Write state back
4. Confirm the override has been cleared
