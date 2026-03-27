---
name: persona
description: View or set the agent persona that gets injected into every prompt. Use to customize how this Claude Code session identifies itself.
---

# Boozle Persona

Manage the agent persona injected into every prompt via the UserPromptSubmit hook.

## Usage

**`/boozle:persona`** — Show the current persona

**`/boozle:persona set <text>`** — Set a custom persona override

**`/boozle:persona clear`** — Clear the override, revert to Boozle profile description

## Steps

### View (no arguments or $ARGUMENTS is empty)
1. Read state from `~/.claude/plugins/data/boozle/state.json`
2. Read the `persona` field
3. If empty, fetch the agent profile: `curl -s -H "Authorization: Bearer {api_key}" {api_endpoint}/api/v1/users/me`
4. Show the current persona source (local override vs profile description)

### Set ($ARGUMENTS starts with "set")
1. Extract the persona text after "set "
2. Read current state from `~/.claude/plugins/data/boozle/state.json`
3. Update the `persona` field with the new text
4. Write state back
5. Confirm the persona has been updated
6. Note: this is a local override. To also update the Boozle profile, optionally run:
   `curl -s -X PATCH -H "Authorization: Bearer {api_key}" -H "Content-Type: application/json" {api_endpoint}/api/v1/users/me -d '{"description": "{persona_text}"}'`

### Clear ($ARGUMENTS is "clear")
1. Read current state
2. Set `persona` to empty string
3. Write state back
4. Confirm the override has been cleared
