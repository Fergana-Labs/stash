# Octopus

Centralized, collaborative memory for teams of AI agents. Every Claude Code session, research paper, webpage, and conversation goes into one shared knowledge base. A sleep agent curates it into a searchable wiki.

## Architecture

Three interaction modes, reflected in the sidebar:

- **Consume** — Files (S3 uploads), History (agent event logs), Tables (structured data)
- **Curate** — Notebooks (wiki with [[backlinks]], sleep agent writes here), Personas (sleep agent + notebook, watches workspace histories filtered by agent_name)
- **Collaborate** — Chats (real-time messaging), Pages (HTML documents, shareable)

Everything lives in a **workspace** — a permissioned container for teams. Personal resources can exist outside workspaces.

## Tech Stack
- Frontend: Next.js 16, React 19, Tailwind 4, TipTap (collaborative editing), Yjs (CRDT)
- Backend: Python, FastAPI, PostgreSQL, pgvector
- CLI: Python, Typer (`cli/main.py`)
- MCP Server: 30+ tools (`mcp_server/server.py`)
- OpenClaw Plugin: Memory injection (`openclaw-plugin/`)
- Real-time: WebSocket, SSE
- Storage: S3-compatible (Cloudflare R2)
- Embeddings: OpenAI text-embedding-3-small (384 dims)
- LLM: Anthropic Claude (sleep agent curation, universal search)

## Key Services
- `backend/services/sleep_service.py` — Background curation agent. Reads workspace histories (filtered by agent_name_filter), notebooks, and tables. Calls Claude to create categorized wiki pages with folders and [[wiki links]]. Persona = sleep agent + notebook.
- `backend/services/universal_search_service.py` — Agentic search loop across all resource types.
- `backend/services/notebook_service.py` — Wiki features: [[link]] parsing, backlinks, page graph, embeddings, auto-index.
- `backend/services/embedding_service.py` — OpenAI embedding API client. Uses EMBEDDING_API_KEY or OPENAI_API_KEY.
- `backend/services/storage_service.py` — S3-compatible file upload/serve.
- `backend/services/ragflow_client.py` — RAGFlow integration for PDF parsing (optional).

## CLI
Installed via `pip install octopus`. Entry point: `cli/main.py`. Key commands:
- `octopus import-bookmarks <file.html>` — Import Chrome/Firefox bookmarks with scraping
- `octopus search <query>` — Universal cross-resource search
- `octopus register/login/auth` — Account management
- `octopus notebooks/history/tables/chats` — Resource CRUD

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Sidebar Information Architecture
```
[Workspace switcher + settings]
Search
── Consume ──     Files, History, Tables
── Curate ──      Notebooks, Personas
── Collaborate ── Chats, Pages
[Docs]
```
