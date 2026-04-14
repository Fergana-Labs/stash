# Octopus

Shared memory for AI agents. Every Claude Code session, research paper, webpage, and conversation goes into one searchable knowledge base. A Claude Code skill ("sleep time compute") organizes it into a wiki.

## Architecture

Three top-level sections in the sidebar:

- **Search** — Universal + semantic search across all resources
- **History** — Append-only event logs grouped by agent_name and session_id
- **Wiki** — Notebooks (wiki pages with [[backlinks]]) and Tables (structured data)

Everything lives in a **workspace** — a permissioned container for teams. Personal resources can exist outside workspaces.

## Tech Stack
- Frontend: Next.js 16, React 19, Tailwind 4, TipTap (collaborative editing), Yjs (CRDT)
- Backend: Python, FastAPI, PostgreSQL, pgvector
- CLI: Python, Typer (`cli/main.py`)
- Real-time: Yjs WebSocket relay (pycrdt), native Python markdown ↔ Yjs conversion
- Storage: S3-compatible (Cloudflare R2)
- Embeddings: OpenAI text-embedding-3-small (384 dims)

## Key Services
- `backend/services/universal_search_service.py` — Agentic search loop across all resource types.
- `backend/services/notebook_service.py` — Wiki features: [[link]] parsing, backlinks, page graph, embeddings.
- `backend/services/embedding_service.py` — OpenAI embedding API client. Uses EMBEDDING_API_KEY or OPENAI_API_KEY.
- `backend/services/yjs_converter.py` — Native Python markdown ↔ Yjs XmlFragment conversion. No Node.js collab server needed.
- `backend/services/storage_service.py` — S3-compatible file upload/serve.

## CLI
Installed via `pip install octopus`. Entry point: `cli/main.py`. Key commands:
- `octopus import-bookmarks <file.html>` — Import Chrome/Firefox bookmarks with scraping
- `octopus search <query>` — Universal cross-resource search
- `octopus login/auth` — Account management (Auth0 + API keys)
- `octopus notebooks/history/tables` — Resource CRUD

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Sidebar Information Architecture
```
Search
History
Wiki (Notebooks + Tables)
```
