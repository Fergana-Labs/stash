# Octopus

Shared memory for AI agents. Every Claude Code session, research paper, webpage, and conversation goes into one searchable knowledge base. A Claude Code skill ("sleep time compute") organizes it into a wiki.

## Architecture

Three top-level sections in the sidebar:

- **Search** — Universal + semantic search across all resources
- **History** — Append-only event logs grouped by agent_name and session_id
- **Wiki** — Notebooks (wiki pages with [[backlinks]]) and Tables (structured data)

Everything lives in a **workspace** — a permissioned container for teams. Personal resources can exist outside workspaces.

## Tech Stack
- Frontend: Next.js 16, React 19, Tailwind 4, TipTap (rich-text editor)
- Backend: Python, FastAPI, PostgreSQL, pgvector
- CLI: Python, Typer (`cli/main.py`)
- Persistence: plain REST PATCH on markdown; no WebSocket, no CRDT
- Storage: S3-compatible (Cloudflare R2)
- Embeddings: OpenAI text-embedding-3-small (384 dims)

## Key Services
- `backend/services/universal_search_service.py` — Agentic search loop across all resource types.
- `backend/services/notebook_service.py` — Wiki features: [[link]] parsing, backlinks, page graph, embeddings.
- `backend/services/embedding_service.py` — OpenAI embedding API client. Uses EMBEDDING_API_KEY or OPENAI_API_KEY.
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

## Working Style

This is an internal tool. Write extremely easy to consume code, optimize for how easy the code is to read. make the code skimmable.  avoid cleverness. use early returns

### Be self-sufficient
If you are about to ask the user to do something for you, think about whether you can do it yourself.

- **Never ask the user to check logs.** Check them yourself — via running the server with captured output, MCPs for hosted servers, or ngrok inspector (`localhost:4040`).
- **Never ask permission to kill/restart local processes.** If you need to restart uvicorn, ngrok, or any dev server to make progress, just do it.
- **Never speculate about env vars, API keys, or config.** If you need to know whether something is set, check it yourself (e.g. `env | grep`, read `.env`, etc.). Just do it. Do not guess or assume. Do not ask the user. Check it yourself.
- **Never ask the user to test UI**. Use the playwright MCP to verify any UI changes that you make for the user. Do not ask the user to check to see if your UI changes worked or not. Use the Playwright MCP, and do it yourself.

### Past Conversation Context

Previous Claude coding sessions are stored as `.jsonl` files in your ~/.claude file. Read these to understand prior decisions, debugging sessions, and context that isn't in git history.
