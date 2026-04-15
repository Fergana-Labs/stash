---
name: connect
description: Set up your Octopus agent name and workspace. Use when starting with Octopus for the first time or reconfiguring the connection.
---

# Octopus Connect

Walk the user through connecting this Claude Code session to Octopus.

## Prerequisites

The `octopus` CLI must be installed (`pip install -e .` from the octopus repo, or `pip install octopus`).

## Steps

1. **Check if CLI is available**: Run `which octopus` to test. If the `octopus` command is not found, install it automatically:
   - Try `pip install -e ${CLAUDE_PLUGIN_ROOT}/..` (installs from the repo root)
   - If that fails, try `pip install octopus` (from PyPI)
   - Verify with `which octopus` again. If still not found, tell the user to install manually and stop.

2. **Check current config**: Run `octopus config` to see if credentials are already set, which scope they're in, and whether a project config already exists. Also check plugin state at `~/.claude/plugins/data/octopus/state.json`.

3. **Pick a config scope**: Ask the user where to save the workspace default:
   - **project** (default): saves to `.octopus/config.json` in the current repo. Hooks only fire with these settings when Claude runs inside this repo. Good for per-project workspaces and keeping other repos untouched.
   - **user**: saves to `~/.octopus/config.json`. Hooks fire with these settings in every Claude session on this machine.
   - Project config overrides user config when both exist.
   - Auth (`api_key`) is always stored at user scope regardless of choice — it's per-machine.
   - Remember the chosen scope — pass `--project` to `octopus config` calls below if the user picked project scope.
   - If project scope: remind the user to add `.octopus/` to their `.gitignore` if they don't want the config committed.

4. **Register or authenticate**: If no API key is configured:
   - Ask if they have an existing Octopus account or need to create one
   - To register: `octopus register <agent_name> --description "description" --json`
   - This stores the API key in `~/.octopus/config.json` automatically (user scope)
   - To use an existing key: `octopus auth <api_endpoint> --api-key <key>`

5. **Verify connection**: `octopus whoami`

6. **Pick a workspace**:
   - List workspaces: `octopus workspaces list --mine --json`
   - If none, create one: `octopus workspaces create "workspace-name" --json`
   - Set as default (add `--project` if project scope was chosen): `octopus config default_workspace <workspace_id> [--project]`

7. **Update plugin config**: Tell the user to update their Octopus plugin settings with the workspace_id value.

8. **Test connectivity**: Push a test event:
   `octopus history push "Octopus plugin connected successfully." --ws <workspace_id> --agent <agent_name> --type session_start`

9. **Confirm**: Report success and summarize the configuration, including which scope (project or user) the workspace setting was saved to.
