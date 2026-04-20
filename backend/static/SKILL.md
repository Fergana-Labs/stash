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

Each surface is exposed twice: `workspace-scoped` and `personal` (no workspace
membership required, owned by the authenticated user).

| Surface | Workspace prefix | Personal prefix |
|---------|------------------|-----------------|
| Users | `/api/v1/users` (register, login, `/me`, `/search`) | — |
| Workspaces | `/api/v1/workspaces` (CRUD, members, invite tokens) | — |
| Notebooks | `/api/v1/workspaces/{ws}/notebooks` | `/api/v1/notebooks` |
| Pages | `/api/v1/workspaces/{ws}/notebooks/{nb}/pages` | `/api/v1/notebooks/{nb}/pages` |
| Folders | `/api/v1/workspaces/{ws}/notebooks/{nb}/folders` | `/api/v1/notebooks/{nb}/folders` |
| Tables | `/api/v1/workspaces/{ws}/tables` | `/api/v1/tables` |
| Rows | `/api/v1/workspaces/{ws}/tables/{t}/rows` | `/api/v1/tables/{t}/rows` |
| Files | `/api/v1/workspaces/{ws}/files` | `/api/v1/files` |
| Memory / History | `/api/v1/workspaces/{ws}/memory/events` | `/api/v1/memory/events` |
| Transcripts | `/api/v1/workspaces/{ws}/transcripts` | — |
| Aggregate (across workspaces) | `/api/v1/me/{notebooks,tables,history-events,decks}` | — |

CRUD verbs are standard: `POST` to create, `GET` list/detail, `PATCH` update,
`DELETE` remove. Semantic-search endpoints hang off their parent resource
(e.g. `GET /notebooks/{nb}/pages/semantic-search?q=...`).

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
- `GET  /files/{id}/text` — extracted text (PDFs with embedded text via
  `pypdf`; plain-text / JSON / XML via UTF-8 decode). Response shape:
  `{"text": ..., "status": "pending|processing|done|failed", "error": ...}`.
  Image OCR and scanned-PDF OCR are not currently supported. Extraction
  runs asynchronously after upload — poll this endpoint until `status`
  is `done` or `failed`.
- `DELETE /files/{id}` — best-effort S3 cleanup plus DB row delete.

## Rate Limits
- Registration: 5/min
- Login: 10/min
- CLI auth session polling: 60/min

## Tips for Agents
- Use the personal route variants for user-private resources; workspace
  variants for shared ones. Membership is enforced.
- For extracted text on an uploaded file, poll `GET /files/{id}/text` — it
  returns `status` alongside the text so you can distinguish "still
  extracting" (`pending`/`processing`) from "done, no text available"
  (`done` with `text: null`).
- Attach files to history events rather than embedding base64 — keeps event
  payloads small and allows reuse across events.
