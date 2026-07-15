# Stash — Files, Skills, and Memory System

## Concept: Your Stash and Skills

**Stash** is your personal home for agent work. Everything you create is scoped
to your account — it is yours alone, with nothing to pick or set up first.
Your Stash has three primary surfaces:

- **Sessions** — agent transcripts uploaded under `/api/v1/me/sessions`.
- **Files** — folders, markdown pages, HTML pages, uploads, and tables.
- **Skills** — modules of agent-usable knowledge: local SKILL.md folders and shareable bundles of sessions and Files.

To give your agents a skill, **create a Files folder** whose immediate children
include a file named `SKILL.md`. The body of `SKILL.md` starts with YAML
frontmatter:

```yaml
---
name: dd-respond
description: Draft response packets to investor diligence asks
when_to_use: When an investor sends a DD checklist
version: 2.1
mcp_exposed: true
---
```

The folder may contain any number of supporting `.md` files (`examples.md`,
`checklist.md`, etc.) — they all become part of the skill payload. Stash
exposes skills via:

- `GET /api/v1/me/skills` — list your skills
- `GET /api/v1/me/skills/{name}` — full skill (SKILL.md + siblings)
- MCP: `stash_list_skills`, `stash_read_skill`

This is the same skills convention Claude Code uses, so a skill authored in
Stash works directly when dropped into any agent's `~/.claude/skills/` folder.

## Overview
Stash is the product surface for you and your agents.

It provides:
- pages organized in nestable folders
- tables (typed columns, rows, CSV import/export, semantic row search)
- session events (with file attachments)
- file uploads (S3-backed; PDF/image text extraction when available)
- Skills for publishing sets of pages, sessions, and files

Design boundary:
- Stash owns persistent state and plugin-based memory access
- external orchestration layers own multi-agent delegation
- Claude-session memory access should go through the Stash plugin, not side-channel polling

## Base URL
`{{PUBLIC_URL}}`

## Authentication
All endpoints (except registration and a few public lookups) require an API key:
```
Authorization: Bearer st_xxxxxxxxxxxxx
```

Your account is the scope. `GET /api/v1/users/me` returns the authenticated
user; everything else hangs off the `/api/v1/me` prefix.

## Quick Start

### 1. Register
```bash
curl -X POST {{BASE_URL}}/api/v1/users/register \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "description": "A helpful assistant"}'
```
Response includes `api_key` — save it, it's shown only once.

### 2. Push a Session Event
```bash
curl -X POST {{BASE_URL}}/api/v1/me/sessions/events \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"cli","event_type":"note","content":"Hello"}'
```

### 3. Create a Page
```bash
curl -X POST {{BASE_URL}}/api/v1/me/pages/new \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Notes","content":"# Hello"}'
```
Pass `"folder_id": "<uuid>"` to drop the page into a specific folder;
omit it to create the page at your root.

### 4. Upload a File
```bash
curl -X POST {{BASE_URL}}/api/v1/me/files \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./report.pdf"
```
Response includes the file `id`, a signed `url`, and basic metadata. For
PDFs with embedded text and text-based documents, extracted text is
available at `GET /api/v1/me/files/{id}/text` once the background extractor
has processed the file (typically a few seconds).

## Route Surfaces

Everything is scoped to your account under `/api/v1/me`. Single shared objects
also have canonical, scope-free URLs (`/api/v1/{pages,files,tables}/{id}`) used
when linking to a specific object by id.

| Surface | Prefix |
|---------|--------|
| User | `/api/v1/users` (register, login, `/me`) |
| Folders (nestable) | `/api/v1/me/folders` |
| Pages | `/api/v1/me/pages` (list) and `/api/v1/me/pages/new` (create) |
| Single page | `/api/v1/pages/{page_id}` |
| Tree (nested folders + pages) | `/api/v1/me/tree` |
| Tables | `/api/v1/me/tables` |
| Single table | `/api/v1/tables/{table_id}` |
| Rows | `/api/v1/me/tables/{t}/rows` |
| Files | `/api/v1/me/files` |
| Single file | `/api/v1/files/{file_id}` |
| Session events | `/api/v1/me/sessions/events` |
| Transcripts | `/api/v1/me/transcripts` |

CRUD verbs are standard: `POST` to create, `GET` list/detail, `PATCH` update,
`DELETE` remove. Semantic search hangs off the page surface
(`GET /api/v1/me/pages/semantic-search?q=...`).

## Page Content (`content_markdown`)

Pages store markdown. The editor implements a **deliberately small
subset** — agents writing content should stick to what's listed below,
since anything else silently passes through as plain text on render.

### Links

Use ordinary markdown links for everything:

| Target | Shape |
|---|---|
| Another page | `[text](/p/<uuid>)` |
| An uploaded file | `[text](/api/v1/me/files/<uuid>/download)` |
| External URL | `[text](https://…)` |

The viewer renders all three with the same style; an `↗` glyph marks
off-origin URLs. Internal `/p/<uuid>` and stash absolute URLs are
SPA-routed (same tab, no reload); externals open in a new tab.

There is no `[[...]]` syntax. Use ordinary markdown links with the page's id URL.

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
4. Images need an absolute URL (external or `/api/v1/me/files/<id>/download`).

## Session Events

Events are structured append-only records keyed by `(agent_name, event_type)`.

```json
POST /api/v1/me/sessions/events
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
wrapper (`stash sessions push --attach ./path`) uploads and attaches in one step.

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
- Everything you create is scoped to your account — your API key is the scope.
- For extracted text on an uploaded file, poll `GET /files/{id}/text` — it
  returns `status` alongside the text so you can distinguish "still
  extracting" (`pending`/`processing`) from "done, no text available"
  (`done` with `text: null`).
- Attach files to session events rather than embedding base64 — keeps event
  payloads small and allows reuse across events.
- When authoring page content that links to another page, use the page id
  URL form: `[text](/p/<uuid>)`.
