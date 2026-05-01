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
  -d '{"tag_name":"cli","event_type":"note","content":"Hello"}'
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

## Page Content (`content_markdown`)

Pages store markdown. The editor implements a **deliberately small
subset** — agents writing content should stick to what's listed below,
since anything else silently passes through as plain text on render.

### Links

Use ordinary markdown links for everything:

| Target | Shape |
|---|---|
| Another page in the same workspace | `[text](/notebooks?ws=<ws>&nb=<nb>&page=<uuid>)` |
| A file uploaded to the workspace | `[text](/api/v1/workspaces/<ws>/files/<uuid>/download)` |
| External URL | `[text](https://…)` |

The viewer renders all three with the same style; an `↗` glyph marks
off-origin URLs. Internal `/notebooks?…` and stash absolute URLs are
SPA-routed (same tab, no reload); externals open in a new tab.

There is no `[[wiki-link]]` syntax. The TipTap editor offers an
autocomplete triggered by typing `[[`, but what it inserts is a
markdown link with the page's id URL — the `[[…]]` brackets never
reach storage.

### Block elements

| Markdown | Rendered as |
|---|---|
| `# Heading` to `### Heading` (H1–H3) | heading |
| blank line | paragraph break |
| `- item` / `* item` / `+ item` | bullet list |
| `1. item` / `2. item` | ordered list |
| `\| col1 \| col2 \|` followed by `\|---\|---\|` | GitHub-flavored pipe table |

Anything starting with `####` (H4+), `>` (blockquote), triple-backtick
code fences, or `---` (hr) is **not parsed** — the markdown renders
literally. Treat it as unsupported.

### Inline

| Markdown | Rendered as |
|---|---|
| `**bold**` | bold |
| `*italic*` | italic |
| `` `code` `` | inline code |
| `![alt](url)` | image (absolute URLs only) |
| `[![alt](src)](href)` | linked image |
| `[text](url)` | link (see above table) |

Strikethrough (`~~`), underline markup, LaTeX, footnotes, and raw HTML
tags are not supported.

### Authoring from agents

When generating page content programmatically, follow these rules and
you'll round-trip cleanly through edit mode:

1. Never emit `[[…]]` — use the id-URL link form.
2. Never emit relative paths like `[text](foo.md)` or `![](foo.jpg)` —
   the renderer treats them as dead and the editor strips them if a
   user saves the page.
3. Don't rely on H4 or deeper headings. Restructure with H3 + bold.
4. Images need an absolute URL (external or `/files/<id>/download`).

## History / Memory Events

Events are structured append-only records keyed by `(workspace, tag_name, event_type)`.

```json
POST /api/v1/workspaces/{ws}/memory/events
{
  "tag_name": "cli",
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
- `GET /events?tag_name=&event_type=&limit=&after=`
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
