# Stash MCP Integration

> **Stash** — shared memory for AI coding agents.  
> This guide explains how to configure any MCP-compatible client to connect to
> the Stash MCP server, giving agents tools for search, VFS browsing, memory,
> and session management.

---

## 1. Overview

Stash provides a Model Context Protocol (MCP) server that exposes your Stash
workspace — files, sessions, connected sources, memory, and skills — as a
discoverable tool set. Any MCP client (Claude Desktop, Fusion agents, Cursor,
VS Code via Continue.dev, or any MCP-compatible application) can connect via
the SSE transport and use these tools to browse, search, and read content from
your Stash.

**Server URL:** `https://joinstash.ai/api/v1/mcp`  
**SSE endpoint:** `https://joinstash.ai/api/v1/mcp/sse`  
**Messages endpoint:** `https://joinstash.ai/api/v1/mcp/messages/`

All tool responses are JSON strings.

---

## 2. Prerequisites

- A Stash account on [joinstash.ai](https://joinstash.ai) (free tier works)
- A Stash API key (`st_…` or legacy `mc_…` prefix)
- An MCP-compatible client (Claude Desktop, Fusion, Cursor, VS Code, or any
  client that supports SSE transport or `uvx`+`mcp-remote`)

---

## 3. Generating an API Key

### Via the Stash Web UI (recommended)

1. Log in at [joinstash.ai](https://joinstash.ai)
2. Navigate to **Settings → API Keys**
3. Click **Create New Key**
4. Choose an access level:
   - **Full access** (`full`) — read and write operations
   - **Read access** (`read`) — reads plus transcript/session upload (for
     production agents that only need to push session logs)
5. Copy the raw key immediately — it is shown only once

### Via the REST API

When password-based auth is enabled (not Auth0), you can register a new user
and get an API key in one call:

```bash
curl -X POST https://joinstash.ai/api/v1/users/register \
  -H "Content-Type: application/json" \
  -d '{"name": "your-username", "password": "your-password", "email": "you@example.com"}'
```

The response includes `api_key` — a `st_`-prefixed token.

For existing users, the UI is the intended path. You can also create additional
keys via:

```bash
curl -X POST https://joinstash.ai/api/v1/users/me/keys \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "mcp-key", "access": "full"}'
```

> ⚠️ The raw key is returned only once. Store it securely. Keys are hashed
> before being persisted — Stash never stores the raw key.

### API Key Format

- Prefix: `st_` (new keys) or `mc_` (legacy keys from the pre-rename era)
- Both prefixes remain valid for as long as the key exists
- Key types: `full` (read + write) and `read` (reads + transcript upload)

---

## 4. Server Configuration

The Stash MCP server uses **Server-Sent Events (SSE)** transport. There is no
stdio transport — all clients must connect via SSE.

| Property | Value |
|----------|-------|
| Mount path | `https://joinstash.ai/api/v1/mcp` |
| SSE endpoint | `https://joinstash.ai/api/v1/mcp/sse` |
| Messages endpoint | `https://joinstash.ai/api/v1/mcp/messages/` |
| Authentication | Bearer token via `Authorization` header |
| Token prefix | `st_` or `mc_` |
| Port | 443 (standard HTTPS) |

Clients that do not support SSE natively can use the
[`mcp-remote`](https://github.com/geelen/mcp-remote) bridge to
wrap the SSE endpoint as a stdio subprocess.

---

## 5. Claude Desktop Configuration

### Option A — Using `uvx mcp-remote` (works with any Claude Desktop version)

Install `mcp-remote` once:

```bash
uv tool install mcp-remote
```

Then add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "stash": {
      "command": "uvx",
      "args": ["mcp-remote", "https://joinstash.ai/api/v1/mcp/sse"],
      "env": {
        "STASH_API_KEY": "st_YOUR_API_KEY_HERE"
      }
    }
  }
}
```

The `STASH_API_KEY` env var is picked up by `mcp-remote` and forwarded as the
`Authorization: Bearer` header.

### Option B — Direct SSE (for clients with native SSE support)

```json
{
  "mcpServers": {
    "stash": {
      "type": "sse",
      "url": "https://joinstash.ai/api/v1/mcp/sse",
      "headers": {
        "Authorization": "Bearer st_YOUR_API_KEY_HERE"
      }
    }
  }
}
```

---

## 6. Fusion Agent Configuration

### MCP Server Settings

In your Fusion project's MCP configuration, add:

```json
{
  "mcpServers": {
    "stash": {
      "transport": "sse",
      "url": "https://joinstash.ai/api/v1/mcp/sse",
      "headers": {
        "Authorization": "Bearer st_YOUR_API_KEY_HERE"
      }
    }
  }
}
```

### Agent Instructions Snippet

Include the following in your Fusion agent's instructions or Prompt.md so the
agent knows how to use the Stash MCP tools:

```
You have access to the Stash MCP server for search, VFS browsing, and memory.

Use `stash_search` to find past work, sessions, and connected-source documents.
Use `stash_vfs_ls` / `stash_vfs_cat` to browse and read files from the VFS.
Use `stash_session_search` to recall past agent sessions by keyword.
Use `get_stash_info` to verify your connection is working.

Always send your Stash API key as `Authorization: Bearer st_YOUR_KEY` in the
MCP Authentication header.
```

---

## 7. Available Tools

All tools are registered in the MCP server at
[`backend/services/mcp_service.py`](../backend/services/mcp_service.py). Each
returns a JSON string.

| Tool | Description | Required Parameters | Optional Parameters |
|------|-------------|-------------------|-------------------|
| `get_stash_info` | Return identity info about the Stash server and authenticated user — includes `user_id`, `client_id`, `scopes`, name, version | — | — |
| `stash_search` | Search across all Stash content accessible to the authenticated user: native files, sessions, connected-source documents, and federated sources | `query` (string) | `limit` (int, default 10) |
| `stash_session_search` | Search the authenticated user's recent sessions by keyword — performs full-text search across session transcript content (user messages, assistant messages, tool calls) and returns matching events with session context. Uses PostgreSQL websearch syntax. | `query` (string) | `limit` (int, default 10) |
| `stash_vfs_ls` | List directory contents in Stash's virtual filesystem. Start with `stash_vfs_ls(path="/")` to discover the top-level sections. | — | `path` (string, default `"/"`) |
| `stash_vfs_cat` | Read a file's text contents from Stash's VFS. Use `stash_vfs_ls` first to discover file paths. | `path` (string) | — |

### VFS Path Format

The Stash virtual filesystem organizes content under these top-level paths:

| Path | Contents |
|------|----------|
| `/` | Root — lists top-level sections |
| `/files/…` | Pages and uploaded files |
| `/sources/<handle>/…` | Connected source documents (GitHub, Notion, Slack, etc.) |
| `/sessions/…` | Agent session transcripts |
| `/memory/…` | Agent-curated Memory wiki |
| `/tables/…` | Table schemas and row data |
| `/skills/…` | Published Skill folders |

### Additional Tools

The MCP server may be extended with additional tools over time. Agents may find
tools such as:

- `stash_session_upload` — upload session transcripts
- `stash_memory_search` — search agent memory
- `stash_memory_append` — append to agent memory

For the canonical, always-up-to-date tool listing, connect any MCP client and
call `get_stash_info`, or inspect the server's tool registration endpoint.

---

## 8. Testing the Connection

Follow these steps to verify your MCP client is properly connected:

### Step 1: Connect

Configure your MCP client with the SSE endpoint and API key (see sections 5–6
above). Restart the client so it fetches the tool list from the server.

### Step 2: Call `get_stash_info`

This is the simplest tool and requires no arguments. It confirms auth is
working and returns basic identity info.

**Expected response** (formatted):
```json
{
  "name": "stash",
  "version": "0.x",
  "user_id": "your-user-uuid",
  "client_id": "your-user-uuid",
  "scopes": ["stash:full"]
}
```

**If you get an error**, see the Troubleshooting section below.

### Step 3: Browse the VFS

```javascript
stash_vfs_ls(path="/")
```

**Expected response** — a directory listing showing the top-level VFS sections:
```json
{
  "path": "/",
  "is_dir": true,
  "entries": ["files", "sessions", "sources", "memory", "tables", "skills", "..."],
  "entry_count": 6,
  "type": "directory"
}
```

### Step 4: Search

```javascript
stash_search(query="test")
```

**Expected response** — a JSON array of results from your Stash content, or an
empty array `[]` if no content matches.

### Step 5: Session Search (optional)

```javascript
stash_session_search(query="deployment")
```

Searches your past agent sessions by keyword. Returns matching events with
session context, or `{"count": 0, "results": []}` if none are found.

---

## 9. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| **401 Unauthorized** | Missing or invalid API key | Verify the key is correct and starts with `st_` (or `mc_` for legacy keys). Generate a new key from **Settings → API Keys** in the Stash UI. |
| **401 on SSE endpoint** | No `Authorization` header sent | Add `"Authorization": "Bearer st_YOUR_KEY"` to your MCP client configuration. If using `uvx mcp-remote`, ensure `STASH_API_KEY` is set in `env`. |
| **"Authentication required"** | Token not passed to tool handler | Ensure your MCP client forwards auth headers with POST requests to the messages endpoint, not just the SSE connection. |
| **SSE connection hangs** | Firewall, proxy, or network issue | Check that outbound HTTPS to `joinstash.ai` on port 443 is allowed. No custom port is needed. |
| **Tool not found** | Outdated client cache | Restart the MCP client to re-fetch the tool list from the server. |
| **"Invalid API key"** | Key was revoked or mistyped | Generate a new key at **Settings → API Keys** in the Stash UI. Keys are shown only once at creation — if lost, revoke the old key and create a new one. |
| **403 Forbidden on write** | Using a read-access key for a mutating operation | Create a new key with `"access": "full"` via **Settings → API Keys**. |
| **Empty results from `stash_search`** | No content indexed yet | Upload files, connect sources (GitHub, Notion, etc.), or use Stash for a few sessions to build up indexable content. |

### Auth Mode Note

Stash supports two authentication modes:

- **API key** (`st_` / `mc_` prefix) — the standard mode documented here. Works
  regardless of whether Auth0 is enabled.
- **Auth0 JWT** (when `AUTH0_ENABLED=true` on the server) — only used by the web
  UI. MCP clients should always use API keys, not JWTs.

---

## 10. Additional Resources

- [Stash](https://joinstash.ai) — shared memory for AI coding agents
- [Model Context Protocol specification](https://modelcontextprotocol.io) —
  the protocol underlying this integration
- [Fusion](https://runfusion.ai) — AI-orchestrated task board
- [`mcp-remote` bridge](https://github.com/geelen/mcp-remote) —
  wraps SSE MCP servers for clients that only support stdio
- Stash API reference — see the [API docs](../backend/routers/README.md) and
  [MCP service source](../backend/services/mcp_service.py)
