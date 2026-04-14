---
name: config
description: View or change Octopus CLI configuration — API key, workspace, history store, defaults.
---

# Octopus Config

View or update the Octopus CLI configuration stored at `~/.octopus/config.json`.

## Usage

### Show current config
Run `octopus config` to display all settings (API key is masked).

### Set a value
Use `octopus config <key> <value>` to update a setting.

Available keys:
- `base_url` — Octopus API endpoint
- `default_workspace` — Default workspace UUID (used when --ws is omitted)
- `default_chat` — Default chat UUID (used when --chat is omitted)
- `default_store` — Default history store UUID (used when --store is omitted)
- `output_format` — Output format: "human" or "json"

### Set API key and endpoint
Use `octopus auth <base_url> --api-key <key>` to set credentials.

### Common workflows

**Switch to a different workspace:**
```bash
octopus workspaces list --mine   # find the workspace ID
octopus config default_workspace <workspace_id>
```

**Switch to a different history store:**
```bash
octopus history list --ws <workspace_id>   # find the store ID
octopus config default_store <store_id>
```

**Switch API key:**
```bash
octopus auth https://getoctopus.com --api-key <new_api_key>
```

## Steps

1. If the user wants to **view** config: run `octopus config`
2. If the user wants to **change** a setting: run `octopus config <key> <value>`
3. If the user wants to **change credentials**: run `octopus auth <url> --api-key <key>`
4. After changes, confirm with `octopus config` and `octopus whoami`
