# Octopus MCP Server

Stdio-transport MCP server exposing Octopus retrieval tools. Works with any
MCP-capable agent — Cursor, Codex CLI, Gemini CLI, Copilot in VS Code,
opencode, Claude Desktop, etc.

Covers **retrieval only**. For activity streaming (recording your sessions
to Octopus history), install the agent-specific plugin alongside — see
`../cursor-plugin/`, `../gemini-plugin/`, etc.

## Install

```bash
pip install "mcp[cli]" httpx
# Optional: log in first so config is picked up automatically
pip install octopus && octopus login
```

## Configure your agent

**Cursor** (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "octopus": { "command": "python3", "args": ["/abs/path/to/server.py"] }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):
```toml
[mcp_servers.octopus]
command = "python3"
args = ["/abs/path/to/server.py"]
```

**Gemini CLI** (`~/.gemini/settings.json` → `mcpServers`):
```json
"octopus": { "command": "python3", "args": ["/abs/path/to/server.py"] }
```

**VS Code / Copilot** (`<workspace>/.vscode/mcp.json`):
```json
{ "servers": { "octopus": { "command": "python3", "args": ["/abs/path/to/server.py"] } } }
```

**Env overrides** (optional):
- `OCTOPUS_API_ENDPOINT` (default: read from CLI config or `https://getoctopus.com`)
- `OCTOPUS_API_KEY` (default: read from CLI config)
- `OCTOPUS_WORKSPACE_ID` (default: `default_workspace` in CLI config)

## Exposed tools

| Tool | What it does |
|---|---|
| `whoami` | Current user profile |
| `list_workspaces` | List your workspaces |
| `query_history` | Recent events in a workspace, filterable by agent/type |
| `search_history` | Full-text search across events in a workspace |
| `list_all_history_events` | Cross-workspace events across every workspace + personal memory |
