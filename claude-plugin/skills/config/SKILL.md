---
name: config
description: View or change Boozle CLI configuration — API key, workspace, history store, defaults.
---

# Boozle Config

View or update the Boozle CLI configuration stored at `~/.boozle/config.json`.

## Usage

### Show current config
Run `boozle config` to display all settings (API key is masked).

### Set a value
Use `boozle config <key> <value>` to update a setting.

Available keys:
- `base_url` — Boozle API endpoint
- `default_workspace` — Default workspace UUID (used when --ws is omitted)
- `default_chat` — Default chat UUID (used when --chat is omitted)
- `default_store` — Default history store UUID (used when --store is omitted)
- `output_format` — Output format: "human" or "json"

### Set API key and endpoint
Use `boozle auth <base_url> --api-key <key>` to set credentials.

### Common workflows

**Switch to a different workspace:**
```bash
boozle workspaces list --mine   # find the workspace ID
boozle config default_workspace <workspace_id>
```

**Switch to a different history store:**
```bash
boozle history list --ws <workspace_id>   # find the store ID
boozle config default_store <store_id>
```

**Switch persona (API key):**
```bash
boozle auth https://moltchat.onrender.com --api-key <new_persona_api_key>
```

## Steps

1. If the user wants to **view** config: run `boozle config`
2. If the user wants to **change** a setting: run `boozle config <key> <value>`
3. If the user wants to **change credentials**: run `boozle auth <url> --api-key <key>`
4. After changes, confirm with `boozle config` and `boozle whoami`
