# Fusion Agent Integration with Stash

> **Stash** — shared memory for AI coding agents.
> This guide shows a Fusion operator how to initialize a Fusion agent so it can
> talk to Stash through two complementary surfaces: the **Stash MCP server**
> (robust tool calling for search, VFS browsing, and memory) and the
> **`FusionSession` logging SDK** (reliable auto-syncing of session transcripts
> to Stash without the agent self-reporting).

A companion, client-agnostic walkthrough lives at
[`docs/stash-mcp-integration.md`](stash-mcp-integration.md). That doc covers
the shared endpoint/auth facts and other clients (Claude Desktop, Cursor, VS
Code). This guide is specifically about **Fusion**, goes deeper on the tool
reference and the logger, and should be read alongside it — it does not repeat
or contradict it.

---

## 1. Overview

Fusion agents get two ways to use Stash:

1. **MCP server (call tools).** Fusion connects to Stash's hosted SSE MCP
   server at `https://joinstash.ai/api/v1/mcp/sse` and authenticates with a
   Stash API key (`st_…` / `mc_…`). The server exposes tools for full-text
   search (`stash_search`, `stash_session_search`, `stash_memory_search`),
   VFS browsing and reading connected sources (`stash_vfs_ls`, `stash_vfs_cat`),
   uploading a session transcript (`stash_session_upload`), appending to the
   persistent Memory wiki (`stash_memory_append`), and verifying the connection
   (`get_stash_info`). The server module is
   [`backend/services/mcp_service.py`](../backend/services/mcp_service.py),
   mounted in [`backend/main.py`](../backend/main.py) with `app.mount`.

2. **Logger (record the run).** A Fusion agent wraps its run with the
   `FusionSession` context manager to auto-capture user / assistant / tool
   messages into a Stash session and upload a transcript on exit. This is the
   "don't make the agent self-report" path — the wrapper does the bookkeeping
   for you.

---

## 2. Prerequisites

- A Stash account on [joinstash.ai](https://joinstash.ai) (free tier works).
- A Stash **API key** with the `full` (read + write) access level for tool
  calling; `read` access is sufficient if you only push session logs. Keys are
  created under **Settings → API Keys** and are shown only once.
  - Prefix: `st_` (new keys) or legacy `mc_`.
  - Key types: `full` (read + write) and `read` (reads + transcript upload).
- A Fusion project / agent with the ability to define MCP server configuration
  and to run Python (for the logger).

---

## Part A — Connect to the Stash MCP Server

### 3. Transport and server endpoints

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

### 4. Fusion MCP config JSON

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

### 5. Verifying the connection

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

### 6. Tool Reference

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

### 7. VFS path format

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

## Part B — Initialize the `FusionSession` Logger

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

### 8. Basic usage

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

### 9. Session lifecycle and the `EventKind` model

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

### 10. Error handling

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

## Configuration Reference

### 11. Where values come from

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

## Local Development

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

## See also

- [`docs/stash-mcp-integration.md`](stash-mcp-integration.md) — the generic,
  client-agnostic MCP guide (endpoint/auth facts, other clients, `uvx mcp-remote`
  bridge).
- [`backend/services/mcp_service.py`](../backend/services/mcp_service.py) — the
  hosted MCP server, its auth model, and the authoritative tool listing.
- `stashai/plugin/hooks.py` and `stashai/plugin/stash_client.py` — the
  auto-sync flow the `FusionSession` logger mirrors.
- `sdk/src/stash_sdk/client.py` — the `Stash` client methods the logger builds
  on (`push_events_batch`, `upload_transcript`, …).