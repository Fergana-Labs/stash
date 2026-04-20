# Stash — Shared Workspace, Notebook, Table, and Memory System

## Overview
Stash is the shared product surface for humans and agents.

It provides:
- workspace membership and permissions
- notebooks (page tree with markdown content, wiki-style backlinks, semantic search)
- tables (typed columns, rows, CSV import/export, semantic row search)
- structured history/memory events (with file attachments)
- file uploads (S3-backed; PDF/image text extraction when available)
- decks (standalone — see deck endpoints)

Design boundary:
- Stash owns persistent shared state and plugin-based memory access
- external orchestration layers own multi-agent delegation
- Claude-session memory access should go through the Stash plugin, not side-channel polling

## Base URL
`{{PUBLIC_URL}}`

## Authentication
All endpoints (except registration and a few public lookups) require an API key:
```
Authorization: Bearer mc_xxxxxxxxxxxxx
```

## Quick Start

### 1. Register
```bash
curl -X POST {{BASE_URL}}/api/v1/users/register \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "description": "A helpful assistant"}'
```
Response includes `api_key` — save it, it's shown only once.

### 2. Create a Workspace
```bash
curl -X POST {{BASE_URL}}/api/v1/workspaces \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Project", "description": "Shared workspace"}'
```

### 3. Push a History Event
```bash
curl -X POST {{BASE_URL}}/api/v1/workspaces/$WS/memory/events \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"cli","event_type":"note","content":"Hello"}'
```

### 4. Create a Notebook Page
```bash
curl -X POST {{BASE_URL}}/api/v1/workspaces/$WS/notebooks/$NB/pages \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Notes","content":"# Hello"}'
```

### 5. Upload a File
```bash
curl -X POST {{BASE_URL}}/api/v1/workspaces/$WS/files \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./report.pdf"
```
Response includes the file `id`, a signed `url`, and basic metadata. For
PDFs with embedded text and text-based documents, extracted text is
available at `GET /api/v1/workspaces/$WS/files/{id}/text` once the
background extractor has processed the file (typically a few seconds).

## Route Surfaces

Every resource lives inside a workspace. There is no personal (no-workspace)
scope — pick or create a workspace first.

| Surface | Prefix |
|---------|--------|
| Users | `/api/v1/users` (register, login, `/me`, `/search`) |
| Workspaces | `/api/v1/workspaces` (CRUD, members, invite tokens) |
| Notebooks | `/api/v1/workspaces/{ws}/notebooks` |
| Pages | `/api/v1/workspaces/{ws}/notebooks/{nb}/pages` |
| Page index (flat, for wiki-link resolution) | `/api/v1/workspaces/{ws}/pages` |
| Folders | `/api/v1/workspaces/{ws}/notebooks/{nb}/folders` |
| Tables | `/api/v1/workspaces/{ws}/tables` |
| Rows | `/api/v1/workspaces/{ws}/tables/{t}/rows` |
| Files | `/api/v1/workspaces/{ws}/files` |
| Memory / History | `/api/v1/workspaces/{ws}/memory/events` |
| Transcripts | `/api/v1/workspaces/{ws}/transcripts` |
| Aggregate (across the user's workspaces) | `/api/v1/me/{notebooks,tables,history-events,decks}` |

CRUD verbs are standard: `POST` to create, `GET` list/detail, `PATCH` update,
`DELETE` remove. Semantic-search endpoints hang off their parent resource
(e.g. `GET /notebooks/{nb}/pages/semantic-search?q=...`).

## Wiki Links (intra-notebook page references)

Page `content_markdown` can embed symbolic references to other pages in the
same workspace using filesystem-like path syntax. These resolve at render
time and survive page renames.

| Syntax | Scope |
|---|---|
| `[[page]]` | current notebook, **current folder only** |
| `[[folder/page]]` | current notebook, named folder |
| `[[notebook/page]]` | named notebook, root |
| `[[notebook/folder/page]]` | fully qualified |

`(notebook_id, folder_id, name)` is unique per migration 0014, so any
well-formed path resolves to at most one page. Unqualified `[[page]]`
does **not** fall back to other folders — if the target lives elsewhere,
qualify it.

Plain markdown links (`[text](https://…)` for external, `[text](/notebooks?ws=…&nb=…&page=…)` for in-app
navigation) are also supported. The viewer renders them with matching
visual treatment — a small `↗` glyph is the only distinction for
off-origin URLs.

## History / Memory Events

Events are structured append-only records keyed by `(workspace, agent_name, event_type)`.

```json
POST /api/v1/workspaces/{ws}/memory/events
{
  "agent_name": "cli",
  "event_type": "note",
  "content": "text body",
  "session_id": "optional",
  "tool_name": "optional",
  "metadata": {},
  "attachments": [
    {"file_id": "<uuid>", "name": "report.pdf", "content_type": "application/pdf"}
  ]
}
```

`attachments` entries must reference a previously-uploaded file. The CLI
wrapper (`stash history push --attach ./path`) uploads and attaches in one step.

Query/search:
- `GET /events?agent_name=&event_type=&limit=&after=`
- `GET /events/search?q=&limit=`
- `GET /events/{event_id}`

## Files

- `POST /files` — multipart upload (field `file`), 50 MB cap.
- `GET  /files` — list.
- `GET  /files/{id}` — metadata (with signed URL).
- `GET  /files/{id}/text` — extracted text. Response shape:
  `{"text": ..., "status": "pending|processing|done|failed", "error": ...}`.
  Works for PDFs with embedded text and for plain-text / JSON / XML
  uploads. Extraction runs asynchronously after upload — poll this
  endpoint until `status` is `done` or `failed`.
- `DELETE /files/{id}` — best-effort S3 cleanup plus DB row delete.

## Rate Limits
- Registration: 5/min
- Login: 10/min
- CLI auth session polling: 60/min

## Tips for Agents
- Every resource requires a workspace — there is no no-workspace scope.
- For extracted text on an uploaded file, poll `GET /files/{id}/text` — it
  returns `status` alongside the text so you can distinguish "still
  extracting" (`pending`/`processing`) from "done, no text available"
  (`done` with `text: null`).
- Attach files to history events rather than embedding base64 — keeps event
  payloads small and allows reuse across events.
- When authoring page content that links to other pages in the same
  workspace, use `[[folder/page]]` / `[[notebook/folder/page]]` wiki
  syntax. Unqualified `[[page]]` only resolves to a sibling in the same
  folder.
