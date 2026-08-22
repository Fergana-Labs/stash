# Stash for Fusion agents (MCP)

This document is the authoritative guide for how a Fusion (or any MCP-capable)
agent initializes and uses Stash's MCP capabilities. It documents the surfaces
that **actually ship** in this repository:

- **Part 1** — the CLI `stdio` MCP server in `cli/mcp_server.py`
  (the `stash-mcp` binary): a 69-tool local server covering the full Stash
  API, plus the per-user backend MCP registry that surfaces through the
  `stash tools` CLI.
- **Part 2** — the hosted SSE MCP server in `backend/services/mcp_service.py`
  (mounted at `/api/v1/mcp`): an 8-tool remote surface for search, VFS,
  and memory.
- **Part 3** — the `FusionSession` logging SDK: auto-syncs session
  transcripts to Stash without the agent self-reporting.

Everything here reflects the real implementation in this repository. If you run
into a cross-referenced symbol that does not match what you see in your tree,
trust the source file over this document and file a task.

A companion, client-agnostic walkthrough lives at
[`docs/stash-mcp-integration.md`](stash-mcp-integration.md). That doc covers
the shared endpoint/auth facts and other clients (Claude Desktop, Cursor, VS
Code). This guide is specifically about **Fusion**, goes deeper on the tool
reference and the logger, and should be read alongside it — it does not repeat
or contradict it.

## What Stash is

Stash is shared memory for AI coding agents. Your agent sessions, memory pages,
connected sources, skills, and tables live in a single account-scoped knowledge
base that any of your coding agents — including Fusion — can read from and write
to through the same MCP endpoint.

Stash exposes MCP capabilities through two servers: a **local CLI `stdio`
server** (Part 1) that serves the full 69-tool surface over standard
input/output, and a **hosted SSE server** (Part 2) that serves an 8-tool core
over the network. A Fusion agent picks one: launch the `stash-mcp` process
as a child for the full local surface, or point its MCP client at the hosted
SSE endpoint for the remote core. The `FusionSession` logger (Part 3) works
with either — it records the run directly to the Stash API.

---

## Part 1 — The CLI `stdio` MCP server (`stash-mcp`)

The full-surface, local option: a `stash-mcp` child process over standard
input/output. All 69 tools are served over that one connection.

### 1. Config loading

The MCP server resolves its credentials through `cli/config.py`'s
`load_config()`. The precedence, from lowest to highest, is:

1. **Built-in defaults** — `cli/config.py` defines `DEFAULT_CONFIG` with
   `base_url = "https://api.joinstash.ai"`.
2. **User config file** — `~/.stash/config.json`. The keys it understands are
   `base_url`, `api_key`, `username`, and `scope`. This file is written by
   `save_config()` (e.g. after you run `stash login`).
3. **Environment variables** — `STASH_URL`, `STASH_API_KEY`, and `STASH_SCOPE`
   override the corresponding config keys.

When the MCP server creates a client (`_client()` in `cli/mcp_server.py`), it
reads the config and builds a `StashClient` with it:

```python
def _client() -> StashClient:
    cfg = load_config()
    return StashClient(cfg["base_url"], cfg.get("api_key", ""), scope=cfg.get("scope", ""))
```

#### Resulting request headers

Every outbound request carries the headers produced by `StashClient._headers()`
in `cli/client.py`:

- `Authorization: Bearer <api_key>` — always sent when an API key is present.
- `X-Stash-Scope: <scope>` — sent only when a `scope` is set. The `scope` is a
  workspace identity; an **empty string or missing scope means your personal
  (default) scope** — sessions/events/searches read and write there.

So a Fusion agent can authenticate either by having a valid `~/.stash/config.json`
on the machine (the common case after `stash login`), or by exporting
`STASH_API_KEY` (and optionally `STASH_URL` / `STASH_SCOPE`) in the environment
of the `stash-mcp` subprocess.

---

### 2. CLI MCP server entry point

The MCP server lives in **`cli/mcp_server.py`**. It constructs the server as:

```python
mcp = FastMCP("stash", instructions="Stash — shared memory for AI coding agents")
```

The console-script entry point is defined in `pyproject.toml`:

```
stash-mcp = "cli.mcp_server:main"
```

and `main()` simply runs the stdio transport:

```python
def main():
    mcp.run(transport="stdio")
```

#### Running it from a Fusion agent

A Fusion agent launches the server as a stdio subprocess by invoking the
`stash-mcp` binary:

```bash
stash-mcp
```

Once launched, the agent speaks the MCP `initialize` handshake and then calls
tools. All 69 tools are served over that stdio connection. Because the server
reads `.mcp.json` wiring (see §4), a Claude Code–style agent can also pick it up
automatically when the registry entry is installed into a project's `.mcp.json`.

#### The 69 tools

`cli/mcp_server.py` registers 69 tools via `@mcp.tool()`. They are grouped
below for navigation. Function names match the shipped `stash_*` functions
exactly.

**Sources, search & VFS**

| Tool | Purpose |
|------|---------|
| `stash_search` | Full-text search across native files, session transcripts, and connected sources |
| `stash_vfs` | Run a read-only shell-shaped script over the whole Stash |
| `stash_list_sources` | List your sources (files, sessions, connected providers) |
| `stash_browse_source` | Browse a source's paths |
| `stash_read_source` | Read one document from a source at a ref |
| `stash_add_source` | Connect a new source |
| `stash_sync_source` | Re-sync a source |
| `stash_remove_source` | Disconnect a source |
| `stash_snapshot_source` | Snapshot a source path into a skill |

**Workspace & session**

| Tool | Purpose |
|------|---------|
| `stash_whoami` | Identify the authenticated user and scope |
| `stash_list_workspaces` | List workspaces and the active scope |
| `stash_switch_workspace` | Switch the active scope (persists to the CLI/plugins) |
| `stash_session_transcript` | Read a session transcript |
| `stash_delete_session` | Delete a session |

**Memory, folders & pages**

| Tool | Purpose |
|------|---------|
| `stash_memory_tree` | Memory wiki as a nested folder/page tree |
| `stash_list_folders` | List folders |
| `stash_create_folder` | Create a folder |
| `stash_edit_folder` | Rename/reparent a folder |
| `stash_delete_folder` | Delete a folder |
| `stash_tree` | The full files tree |
| `stash_list_pages` | List pages |
| `stash_read_page` | Read a page |
| `stash_create_page` | Create a page |
| `stash_edit_page` | Edit a page |
| `stash_delete_page` | Delete a page |
| `stash_copy_page` | Copy a page |
| `stash_copy_folder` | Copy a folder |
| `stash_copy_file` | Copy a file |
| `stash_batch_move` | Move multiple items in one call |
| `stash_batch_delete` | Delete multiple items in one call |
| `stash_batch_restore` | Restore multiple items in one call |

**Tables**

| Tool | Purpose |
|------|---------|
| `stash_list_tables` | List tables |
| `stash_create_table` | Create a table |
| `stash_delete_table` | Delete a table |
| `stash_table_schema` | Read a table's schema |
| `stash_query_table` | Query a table |
| `stash_insert_row` | Insert a row |
| `stash_update_row` | Update a row |
| `stash_delete_row` | Delete a row |
| `stash_add_column` | Add a column |
| `stash_delete_column` | Delete a column |
| `stash_update_table` | Update table metadata |
| `stash_export_table` | Export a table |

**Skills**

| Tool | Purpose |
|------|---------|
| `stash_list_skills` | List your skills |
| `stash_read_skill` | Read a skill |
| `stash_create_skill` | Create a skill |
| `stash_update_skill` | Update a skill |
| `stash_publish_skill` | Publish a skill |
| `stash_unpublish_skill` | Unpublish a skill |
| `stash_get_shared_skill` | Get a shared skill by slug |
| `stash_fork_skill` | Fork a skill by slug |
| `stash_search_public_skills` | Search public skills |
| `stash_read_public_skill` | Read a public skill by slug |

**Files**

| Tool | Purpose |
|------|---------|
| `stash_list_files` | List files |
| `stash_file_text` | Read a file's text |
| `stash_upload_file` | Upload a file |
| `stash_edit_file` | Edit a file |
| `stash_delete_file` | Delete a file |

**Publishing**

| Tool | Purpose |
|------|---------|
| `stash_publish_html` | Publish an HTML document |
| `stash_publish_markdown` | Publish a markdown document |

**Events & agents**

| Tool | Purpose |
|------|---------|
| `stash_query_events` | Query events |
| `stash_push_event` | Push an event |
| `stash_list_agents` | List your agents |

**Trash, shares & restore**

| Tool | Purpose |
|------|---------|
| `stash_list_trash` | List items in the trash |
| `stash_restore` | Restore a trashed item |
| `stash_purge` | Permanently purge a trashed item |
| `stash_share_object` | Share an object |
| `stash_unshare_object` | Unshare an object |
| `stash_list_shares` | List an object's shares |

> Note: the table above is the complete 69-tool roster as shipped. If you spot a
> `stash_*` tool in this document's list that does not exist in your tree's
> `cli/mcp_server.py`, trust the source file and file a task.

---

### 3. Key tool examples

Three tools deserve a closer look because they are the primary entry points a
Fusion agent will use day-to-day. Signatures and return shapes below are taken
verbatim from their docstrings in `cli/mcp_server.py` and the underlying
`StashClient` methods in `cli/client.py`.

#### `stash_search`

```python
stash_search(
    query: str,
    source: str = "",
    include_sources: str = "",
    exclude_sources: str = "",
    limit: int = 20,
    modified_after: str = "",
    modified_before: str = "",
) -> str
```

Searches across all your sources — native files + session transcripts +
connected sources (GitHub/Drive/Gmail/Notion/Slack/Granola) — merged onto one
relevance scale. Returns a JSON-encoded `{"results": [...], "has_more": bool}`.
`has_more` means more matched than `limit` — raise `limit` to see them.

**Source scoping**

- Pass `source` to scope to one source (a handle from `stash_list_sources`:
  `'files'`, `'sessions'`, or a connected-source id); omit it to search
  everything.
- Or filter with comma-separated `include_sources`/`exclude_sources` (native
  handles + provider names, e.g. `"files,gmail"`); not combinable with `source`.
- Comma-separated filter strings are split into token lists by
  `split_source_tokens()` in `cli/client.py` (blank input → no filter).
- Pass `modified_after`/`modified_before` (ISO-8601) to restrict to a
  last-modified window; results with no known modification time are excluded
  whenever a bound is set.

The underlying call is `StashClient.search_sources(...)`, which issues
`GET /api/v1/me/sources/search` and returns the same envelope.

#### `stash_vfs`

```python
stash_vfs(script: str, cwd: str = "/") -> str
```

Runs one read-only shell-shaped script over your whole Stash — `ls`, `cat`,
`find`, `grep`/`rg`, `tree`, pipes — exactly like `stash vfs` in a terminal.
Roots include `/files`, `/sessions`, `/skills`, `/memory`, `/sources`.

Returns a JSON-encoded `{"stdout": ..., "stderr": ..., "exit_code": ...}` from
`StashClient.run_vfs` (`POST /api/v1/me/vfs`). **A non-zero `exit_code` is a
shell result (e.g. grep found nothing), not an error** — read `stdout`/`stderr`
like a terminal would show them.

The script is executed server-side by the `stashvfs/` package, which exports
`VfsClient`, `StashVfsModel`, `MachineVfsClient`, `VfsClientError`,
`VfsCommandResult`, `VfsScanBudget`, `SkillAppVfsShell`, and `MountError`.

#### `stash_memory_tree`

```python
stash_memory_tree() -> str
```

Returns the Memory wiki as a nested folder/page tree, rooted at your Memory
folder, as a JSON-encoded structure from `StashClient.get_memory_tree`
(`GET /api/v1/me/memory-tree`).

The Files tree (`stash_tree`) deliberately hides this subtree, so this is how
you discover memory pages; read one with `stash_read_page`. (The related
`StashClient.get_memory_folder()` → `GET /api/v1/me/memory-folder` returns just
the memory folder root object.)

#### Suggested flow for a Fusion agent

1. **Authenticate** — ensure either `~/.stash/config.json` has a valid
   `api_key`, or export `STASH_API_KEY` (optionally `STASH_URL` / `STASH_SCOPE`).
2. **Launch** `stash-mcp` as a stdio subprocess.
3. **Call tools** — e.g. `stash_search` to find relevant context, `stash_vfs`
   to inspect the tree with shell scripts, `stash_memory_tree` to discover and
   then `stash_read_page` to read memory pages.

---

### 4. Backend registry contract

Stash maintains a **per-user MCP-server registry** in the backend. This is a
private registry — there is no sharing surface; each entry belongs to its
owner.

#### REST API

The registry is served by `backend/routers/mcp_servers.py`, mounted as
`app.include_router(mcp_servers.router)` in `backend/main.py`. The router uses
`APIRouter(prefix="/api/v1/me", tags=["mcp-servers"])` and exposes:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/me/mcp-servers` | List the current user's registered MCP servers |
| `POST` | `/api/v1/me/mcp-servers` | Create an MCP server (returns `201`) |
| `DELETE` | `/api/v1/me/mcp-servers/{server_id}` | Delete an MCP server (returns `204`) |

The `POST` body is the `McpServerCreate` model:

```python
name: str      # length 1..100, matches ^[a-zA-Z0-9][a-zA-Z0-9_-]*$; becomes the mcpServers key
transport: Literal["stdio", "http"]
command: str | None   # stdio launch command
url: str | None       # http endpoint URL
headers: dict[str, str] = {}
env: dict[str, str] = {}
```

A `model_validator` (`check_transport_fields`) enforces the transport contract:

- **stdio** requires `command`; `url`/`headers` are rejected (takes `command`/`env` only).
- **http** requires a `url` starting with `http://` or `https://`; `command`/`env` are rejected (takes `url`/`headers` only).

#### The `stash tools` CLI surface

The registry is surfaced through the `stash tools` CLI subcommand group in
`cli/main.py` (`stash tools add|list|install|remove`):

- `stash tools add <name> --command ...` (stdio) or `stash tools add <name> --url ...` (http, with repeatable `--header KEY=VAL`, and `--env KEY=VAL` for stdio). Registers the server in the backend.
- `stash tools list` — lists your registered servers.
- `stash tools install <name>` — writes the registered server into this project's `.mcp.json` so Claude Code / Fusion agents pick it up.
- `stash tools remove <name>` — removes a registered server.

#### How `.mcp.json` gets written

`stash tools install <name>` reads the registered server and builds a Claude
Code–compatible `mcpServers` entry via `_mcp_json_entry()` in `cli/main.py`:

- **stdio:** `{ "type": "stdio", "command": <argv[0]>, "args": <remaining argv>, "env": {...} }`
- **http:** `{ "type": "http", "url": <url>, "headers": {...} }`

`_merge_mcp_server()` merges the entry into `Path.cwd() / ".mcp.json"` under the
`mcpServers` key. Ownership is tracked in a top-level marker key,
`stashManagedServers` — `stash tools install` sweeps and rewrites only entries
stash manages, and never touches user-added ones (a name collision with a
user-defined server is a conflict, not a clobber).

Because a Fusion agent reads the project's `.mcp.json` for its stdio servers,
installing the registered `stash-mcp` entry into the project wires the agent to
Stash automatically.

#### The Tools page

The product's Tools page also reads this same per-user registry
(`GET /api/v1/me/mcp-servers`), so a server added via the CLI appears there and
vice versa — same backing store, two surfaces.

---

## Part 2 — The hosted SSE MCP server

The remote option: Stash's hosted SSE MCP server — an 8-tool core surface
for search, VFS, and memory, served over the network at
`https://joinstash.ai/api/v1/mcp`.

### 5. Prerequisites

- A Stash account on [joinstash.ai](https://joinstash.ai) (free tier works).
- A Stash **API key** with the `full` (read + write) access level for tool
  calling; `read` access is sufficient if you only push session logs. Keys are
  created under **Settings → API Keys** and are shown only once.
  - Prefix: `st_` (new keys) or legacy `mc_`.
  - Key types: `full` (read + write) and `read` (reads + transcript upload).
- A Fusion project / agent with the ability to define MCP server configuration
  and to run Python (for the logger).

---

### 6. Transport and server endpoints

Stash's MCP server speaks **Server-Sent Events (SSE)** transport only — there
is no stdio transport for the hosted server. (The standalone local/CLI server
at `cli/mcp_server.py` is a separate surface for local development; it is not
the hosted server this section configures.)

| Property | Value |
|----------|-------|
| Mount path | `https://joinstash.ai/api/v1/mcp` |
| SSE endpoint | `https://joinstash.ai/api/v1/mcp/sse` |
| Messages endpoint | `https://joinstash.ai/api/v1/mcp/messages/` |
| Transport | SSE |
| Authentication | `Authorization: Bearer st_…` header |
| Token prefix | `st_` or `mc_` |

---

### 7. Fusion MCP config JSON

In your Fusion project's MCP configuration, register a `stash` server. The
exact JSON shape matches Fusion's standard `mcpServers` block:

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

Replace `st_YOUR_API_KEY_HERE` with a real key (`st_…` or `mc_…`). The bearer
token goes in the `Authorization` header — it is **never** placed in the URL.
Fusion's client opens the SSE stream, receives the message endpoint from the
server, and POSTs tool invocations to `/api/v1/mcp/messages/`.

---

### 8. Verifying the connection

Give the Fusion agent these instructions so it can confirm the link and use the
tools correctly:

```text
You have access to the Stash MCP server for search, VFS browsing, and memory.

Verify your connection with `get_stash_info` before relying on the tools.
Use `stash_search` to find past work, sessions, and connected-source documents.
Use `stash_vfs_ls` / `stash_vfs_cat` to browse and read files from the VFS.
Use `stash_session_search` to recall past agent sessions by keyword.
Use `stash_memory_search` to search the agent-curated Memory wiki.
Use `stash_memory_append` to persist durable notes into the Memory wiki.
Use `stash_session_upload` to push an already-recorded session transcript.

Every tool returns a JSON string; parse it before acting on the result.
```

---

### 9. Tool reference

All eight tools below are registered in the MCP server at
[`backend/services/mcp_service.py`](../backend/services/mcp_service.py). Each
returns a **JSON string**. Required and optional parameters come from the
function signatures in that module.

| Tool | Description | Required parameters | Optional parameters |
|------|-------------|---------------------|---------------------|
| `get_stash_info` | Return identity info about the Stash server and the authenticated user — includes `user_id`, `client_id`, `scopes`, name, version | — | — |
| `stash_search` | Search across all Stash content accessible to the authenticated user: native files, sessions, connected-source documents, and federated sources | `query` (string) | `limit` (int, default 10) |
| `stash_session_search` | Full-text search of the authenticated user's recent session transcripts (user messages, assistant messages, tool calls); returns matching events with session context | `query` (string) | `limit` (int, default 10) |
| `stash_memory_search` | Search the authenticated user's Memory wiki pages by keyword | `query` (string) | `scope` (`"agent"` / `"project"`), `layer` (`"long-term"` / `"daily"`), `limit` (int, default 5) |
| `stash_vfs_ls` | List directory contents in Stash's virtual filesystem; start with `path="/"` to discover the top-level sections | — | `path` (string, default `"/"`) |
| `stash_vfs_cat` | Read a file's text contents from the VFS; use `stash_vfs_ls` first to discover file paths | `path` (string) | — |
| `stash_session_upload` | Upload a session transcript to Stash (session metadata + a JSON array of events), making it searchable; supports idempotent `replace` | `session_id` (string) | `agent_name` (string), `cwd` (string), `events` (JSON string, default `"[]"`), `replace` (bool, default false) |
| `stash_memory_append` | Append Markdown content to the authenticated user's persistent Memory wiki page for a `(scope, layer)` pair (e.g. `project-long-term`); creates the page if it does not exist | `scope` (`"agent"` / `"project"`), `layer` (`"long-term"` / `"daily"`), `content` (string) | — |

---

### 10. VFS path format

The virtual filesystem organizes content under these top-level paths (used by
`stash_vfs_ls` / `stash_vfs_cat`):

| Path | Contents |
|------|----------|
| `/` | Root — lists top-level sections |
| `/files/…` | Pages and uploaded files |
| `/sources/<handle>/…` | Connected source documents (GitHub, Notion, Slack, etc.) |
| `/sessions/…` | Agent session transcripts |
| `/memory/…` | Agent-curated Memory wiki |
| `/tables/…` | Table schemas and row data |
| `/skills/…` | Published Skill folders |

---

## Part 3 — The `FusionSession` logger

The logger is a Python context manager delivered by the **`stash-sdk`** package
(module `sdk/src/stash_sdk/session_store.py`). It wraps a Fusion run so that
user, assistant, and tool events are captured into a Stash session and the
transcript is uploaded when the run exits — the agent never has to self-report.

> **Status note.** The SDK ships with the `stash-sdk` package on the
> `stash-sdk` distribution (`Stash` and `StashError` are already exported from
> `sdk/src/stash_sdk/__init__.py`). The `FusionSession` wrapper and its
> `Stash.create_session` client method are the **intended API surface** provided
> by the SDK shipment; they are documented here as designed. If your installed
> version already exports `FusionSession`, the exact signatures below apply;
> otherwise the API is the one specified here.

### 11. Basic usage

```python
from stash_sdk import Stash, FusionSession

with FusionSession(
    agent_name="fusion",
    api_key="st_YOUR_API_KEY_HERE",
    base_url="https://api.joinstash.ai",
    cwd="/path/to/repo",
) as s:
    s.log_user_message("Hello!")           # event_type="user_message"
    s.log_tool_use("search", results)      # event_type="tool_use"
    s.log_assistant_message("Found it!")   # event_type="assistant_message"
```

- **`__enter__`** calls `Stash.create_session()` (a `POST /api/v1/me/sessions`
  upsert) so the `session_id`, `agent_name`, `cwd`, and `files_touched` are
  locked in at session start. It returns the `FusionSession` itself.
- **`log_user_message(text)`** records an event with `event_type="user_message"`.
- **`log_assistant_message(text)`** records an event with
  `event_type="assistant_message"`.
- **`log_tool_use(tool_name, result)`** records an event with
  `event_type="tool_use"`.
- A generic `log_event(...)` accepts arbitrary fields (`session_id`,
  `agent_name`, `event_type`, `content`, `tool_name`, `metadata`).

Each `log_*` call appends an event dict to an in-memory buffer **and** to a
crash-safe local JSONL backstop file, then flushes the buffer via
`Stash.push_events_batch()` when the buffer reaches a batch threshold or enough
time has elapsed since the last flush. On exit it uploads the backstop file as
the gzipped transcript.

---

### 12. Session lifecycle and the `EventKind` model

The logger's events mirror Stash's canonical lifecycle, defined by the
`EventKind` literal in `stashai/plugin/event.py`:

| Stash `EventKind` | Meaning | `FusionSession` mapping |
|-------------------|---------|-------------------------|
| `session_start` | A session begins | session created in `__enter__` via `create_session` |
| `prompt` | A user prompt is recorded | `log_user_message` |
| `tool_use` | A tool call / response is recorded | `log_tool_use` |
| `stop` | The agent finishes responding | `log_assistant_message` / final assistant output |
| `session_end` | The session ends | `__exit__` flushes events and uploads the transcript |

These map onto the auto-sync flow the Claude/Codex/Hermes hooks already use:
`create_session_record` and `finalize_session_upload` in
[`stashai/plugin/hooks.py`](../stashai/plugin/hooks.py), backed by
`StashClient.create_session` in
[`stashai/plugin/stash_client.py`](../stashai/plugin/stash_client.py). The
logger reuses the same endpoints: `POST /api/v1/me/sessions` to create the row,
`POST /api/v1/me/sessions/events/batch` to flush buffered events, and
`POST /api/v1/me/transcripts` to upload the transcript.

---

### 13. Error handling

The logger is deliberately **crash-safe** and **best-effort**:

- **Crash-safe backstop.** Every event is written to
  `~/.stash/sessions/<session_id>.jsonl` before it is buffered. A mid-run crash
  or network outage never loses events — the file is the durable record and is
  re-uploaded on the next exit. The path is overridable via a `data_dir`
  argument (used by tests).
- **Suppressed network errors.** Buffer-flush and transcript-upload failures are
  caught, logged as warnings, and suppressed so the Fusion agent's run is never
  interrupted by a Stash outage. This is the one deliberate exception to the
  repo's "fail loud" rule (see `AGENTS.md`): a logging wrapper must never crash
  the thing it is logging.
- **Sessions are never deleted on exit.** Stash keeps the history.
- **Local/CLI tooling fail loud** where it matters. The plugin hooks that mirror
  this flow (`create_session_record`, `finalize_session_upload`) stay
  best-effort for the same reason.

---

## Configuration reference

### 14. Where values come from

Fusion agents and the logger read the same configuration sources the rest of
Stash uses:

- **User config file** — `~/.stash/config.json` (managed by
  [`cli/config.py`](../cli/config.py)), with keys `base_url`, `api_key`, and
  `username`.
- **Environment override** — the `STASH_API_KEY` environment variable overrides
  `api_key` when set.
- **Per-agent config** — the agent plugins resolve values via
  [`stashai/plugin/agent_config.py`](../stashai/plugin/agent_config.py):
  `get_config` returns `api_endpoint` (defaults to the production base URL),
  `api_key`, and `agent_name`; `data_dir_from_env` derives the local data
  directory from an env var plus a default subpath; `is_configured` tells you
  whether a client is ready to use.

Common values:

| Setting | Example | Source |
|---------|---------|--------|
| `base_url` | `https://api.joinstash.ai` | `~/.stash/config.json` (`base_url`) or `PRODUCTION_BASE_URL` |
| `api_key` | `st_…` / `mc_…` | `~/.stash/config.json` (`api_key`) or `STASH_API_KEY` env var |
| `username` / `agent_name` | `fusion` | `~/.stash/config.json` (`username`) |

If `base_url` is omitted, the default is the production API
(`https://api.joinstash.ai`), which is the correct base for the hosted MCP
server and the logger.

---

## Local development

To point a Fusion agent or the logger at a **local** Stash backend instead of
the hosted one:

- Run the Stash backend locally (see the repo README for the local stack) so
  the MCP sub-application mounts at `/api/v1/mcp`.
- Set the Fusion MCP config `url` to your local SSE endpoint, e.g.
  `http://localhost:3456/api/v1/mcp/sse`, and use a local API key.
- Pass `base_url="http://localhost:3456"` to `FusionSession` (or set
  `base_url` in `~/.stash/config.json`).
- For purely local experiments separate from the hosted SSE server, the repo's
  `cli/mcp_server.py` provides a standalone stdio server — this is a separate
  local/CLI surface, not the hosted SSE server, and is not what Fusion connects
  to in production.

---

## What did NOT ship (disambiguation)

- **The hosted SSE server postdates this document's original write-up.**
  Part 1 was written against `origin/main` @ `10d06d55` (STAS-097), when the
  CLI `stdio` server was the only shipped MCP surface; at that time there was
  no hosted remote endpoint, and hosted-SSE documentation reflected an
  unshipped design. That surface has since shipped on `main`
  (`backend/services/mcp_service.py`, mounted at `/api/v1/mcp`), so Part 2 is
  now accurate and the older "no hosted endpoint" guidance is obsolete.
- **Session-folder tools are gone.** `stash_list_session_folders`,
  `stash_create_session_folder`, and `stash_assign_session` were removed from
  `cli/mcp_server.py` when session folders were retired; the roster in §2 is
  the current 69-tool list.
- **STAS-007 tool names never shipped.** If you encounter documentation
  referencing tools named `stash_vfs_list` / `stash_vfs_read` /
  `stash_memory_store` / `stash_memory_retrieve`, those reflect a *planned*,
  never-shipped design and should be ignored in favor of this document.
- **The registry is a registry, not a proxy.** The per-user MCP-server
  registry (`/api/v1/me/mcp-servers`) stores launch configuration for MCP
  servers; it is not itself a remote MCP server, and it does not proxy calls
  to Stash.

## See also

- [`docs/stash-mcp-integration.md`](stash-mcp-integration.md) — the generic,
  client-agnostic MCP guide (endpoint/auth facts, other clients, `uvx mcp-remote`
  bridge).
- [`cli/mcp_server.py`](../cli/mcp_server.py) — the CLI `stdio` MCP server:
  the authoritative 69-tool roster and its config loading.
- [`backend/services/mcp_service.py`](../backend/services/mcp_service.py) — the
  hosted MCP server, its auth model, and the authoritative tool listing.
- `stashai/plugin/hooks.py` and `stashai/plugin/stash_client.py` — the
  auto-sync flow the `FusionSession` logger mirrors.
- `sdk/src/stash_sdk/client.py` — the `Stash` client methods the logger builds
  on (`push_events_batch`, `upload_transcript`, …).
