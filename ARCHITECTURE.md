# Architecture

## System overview

Stash is a collaborative memory platform for AI agent teams. Three layers: a Next.js frontend, a FastAPI backend, and PostgreSQL with pgvector for storage.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Clients                                     │
│                                                                      │
│   ┌─────────────┐              ┌──────────────────────────┐          │
│   │ Next.js UI  │              │ Claude plugin            │          │
│   │ (browser)   │              │   hooks  ──▶ REST        │          │
│   │             │              │   skills ──▶ stash CLI │          │
│   └──────┬──────┘              └─────────┬──────────┬─────┘          │
│          │ REST                          │ shell    │ REST           │
│          │                       ┌───────┴────────┐ │                │
│          │                       │  stash CLI   │ │                │
│          │                       └───────┬────────┘ │                │
│          │                               │ REST     │                │
└──────────┼───────────────────────────────┼──────────┼────────────────┘
           │                               │          │
           ▼                               ▼          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (:3456)                          │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐            │
│  │ Routers  │ │ Services │ │ Auth     │ │ Rate limit   │            │
│  │ (REST)   │ │ (logic)  │ │ (API key │ │ (slowapi)    │            │
│  │          │ │          │ │  + JWT)  │ │              │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘            │
│                                                                      │
│  Async side-effects (fire-and-forget tasks):                         │
│    • Embedding generation on page / row / event write                │
│    • Wiki link extraction + resolution on page write                 │
│    • Webhook delivery with exponential-backoff retry                 │
│                                                                      │
│  No long-lived background loops. No LLM inference in the backend —   │
│  curation and universal search live in plugin skills on the client.  │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                PostgreSQL 16 + pgvector                               │
│                                                                      │
│  Identity:   users, workspaces, workspace_members                    │
│  Content:    notebooks, notebook_folders, notebook_pages,            │
│              page_links, history_events, tables, table_rows,         │
│              files, documents, decks                                  │
│  Chat:       chats, chat_messages                                     │
│  Sharing:    object_permissions, object_shares,                      │
│              deck_shares, deck_share_views, deck_share_page_views    │
│  Webhooks:   webhooks, webhook_deliveries                            │
│  Analytics:  embedding_projections                                    │
│                                                                      │
│  Indexes: GIN (FTS on content), HNSW (vector cosine similarity)      │
└──────────────────────────────────────────────────────────────────────┘
```

## Product split

Stash is the shared system of record — users, workspaces, notebooks, history, chats, tables, files, decks, permissions. If state is shared, persisted, or user-visible, it belongs here.

External orchestration layers (multi-agent frameworks, local bridge daemons, the Claude plugin in `plugins/claude-plugin/`) integrate with Stash by pushing history events, syncing notebooks, and reading resources via REST / CLI.

## Data model

### Core entities

```
workspaces ─┬── workspace_members ──── users
             │
             ├── notebooks
             │    ├── notebook_folders
             │    ├── notebook_pages (embedding, FTS, wiki-links)
             │    └── page_links
             │
             ├── history_events (embedding, FTS)
             │
             ├── chats
             │    └── chat_messages (FTS)
             │
             ├── tables
             │    └── table_rows (embedding)
             │
             ├── decks
             │    └── deck_shares
             │         └── deck_share_views
             │              └── deck_share_page_views
             │
             ├── files
             │    └── documents (optional RAGflow link)
             │
             ├── webhooks
             │    └── webhook_deliveries
             │
             └── object_permissions
                  object_shares
```

`history_events` lives directly under a workspace (no intermediate "store" abstraction). Grouping in the UI is by `agent_name` + `session_id` on the event row.

### Workspace scoping

Every content resource (notebooks, history_events, chats, tables, decks, files) has an optional `workspace_id` foreign key:

- **`workspace_id IS NOT NULL`** — workspace resource, governed by membership and permissions
- **`workspace_id IS NULL`** — personal resource, owned by `created_by` / `uploaded_by`

This dual-mode design lets users keep private resources alongside shared workspace content using the same tables and API structure. The `/api/v1/me/*` aggregate router exposes cross-workspace views of a user's personal + accessible resources.

### Permission model

Two tables enforce fine-grained access for `chat`, `notebook`, `history`, `deck`, `table`:

| Table | Key | Purpose |
|-------|-----|---------|
| `object_permissions` | `(object_type, object_id)` | Visibility: `inherit` (workspace members), `private` (explicit shares only), `public` (anyone) |
| `object_shares` | `(object_type, object_id, user_id)` | Per-user grants: `read`, `write`, `admin` |

Workspace roles (`owner`, `admin`, `member`) provide the base access tier. Object-level permissions layer on top.

### Deck sharing

Decks ship with their own public-facing share system independent of object permissions. A `deck_shares` row mints a token-based URL with optional passcode, email-gate, expiry, and download control. Each anonymous session gets a `deck_share_views` row; per-slide dwell time lands in `deck_share_page_views`.

### Vector search

Three tables carry `vector(384)` embedding columns indexed with HNSW (cosine similarity):

- `notebook_pages.embedding` — semantic page search
- `history_events.embedding` — semantic event search
- `table_rows.embedding` — semantic row search

Embeddings are generated asynchronously via a pluggable provider (OpenAI-compatible, Hugging Face Inference API, local sentence-transformers, or bring your own). Set `EMBEDDING_PROVIDER` in `.env`; defaults to auto-detect.

## Backend architecture

### Router / Service separation

```
HTTP Request
    │
    ▼
Router (routers/*.py)
    │  • Input validation (Pydantic)
    │  • Auth: get_current_user dependency (API key or JWT)
    │  • Membership / ownership checks
    │  • Rate limit decorators where applicable
    │  • Delegates to service layer
    │
    ▼
Service (services/*.py)
    │  • Business logic
    │  • Database queries (asyncpg)
    │  • No HTTP concerns
    │
    ▼
Database (database.py)
       • asyncpg connection pool
       • Raw SQL with parameterized queries ($1, $2, ...)
```

Most routers are split into `ws_router` (workspace-scoped, `/workspaces/{id}/...`) and `personal_router` (personal resources, `/me/...`).

### Routers

| Router | Mount | Responsibility |
|--------|-------|---------------|
| `users` | `/users` | Register, login, API key issuance, profile |
| `workspaces` | `/workspaces` | Workspace CRUD, membership, invites |
| `notebooks` | workspace + personal | Notebook, folder, page, wiki-link CRUD |
| `memory` | workspace + personal | History event push, query, FTS, vector search |
| `tables` | workspace + personal | Tables, rows, columns, CSV import/export |
| `files` | workspace + personal | Uploads, downloads, signed URLs |
| `aggregate` | `/api/v1/me/*` | Cross-workspace personal views + analytics |
| `skill` | `/skill/stash/SKILL.md` | Serves the plugin skill manifest |

### Services

| Service | Responsibility |
|---------|---------------|
| `user_service` | Account CRUD, password auth (bcrypt), API key issuance |
| `workspace_service` | Workspace CRUD, membership, invite codes, role enforcement |
| `notebook_service` | Notebooks, pages, folders, wiki links, page graph, embeddings |
| `memory_service` | History events: push (single + batch), query, FTS, vector search |
| `table_service` | Tables, rows, columns, CSV import/export, row embeddings |
| `permission_service` | Visibility, shares, access checks |
| `embeddings` | Pluggable embedding providers (OpenAI-compat, HuggingFace, local, BYO) |
| `storage_service` | S3-compatible file upload and serve (local fallback) |
| `analytics_service` | Dashboard views: activity timeline, key topics, embedding projection |

### Auth

Two credential types accepted on the same endpoints:

- **API key** — issued at registration; sent as `Authorization: Bearer <key>`. Stored as a SHA-256 hash in `users.api_key_hash`.
- **JWT** — issued by `/users/login`; used by the web UI.

`get_current_user` resolves either.

### Rate limiting

`slowapi` backs per-route limits. Currently enforced on:

- `POST /users/register` — 5/min per IP
- `POST /users/login` — 10/min per IP

### Webhooks

A workspace user can register one outbound webhook per workspace (`webhooks` table, unique on `(workspace_id, user_id)`). On qualifying events:

1. Payload is enqueued in `webhook_deliveries` with `status='pending'` and `next_retry_at=now()`.
2. A fire-and-forget delivery task signs the payload with HMAC-SHA256 (`X-Webhook-Signature` header) using the per-webhook secret.
3. On HTTP failure, the row is rescheduled with exponential backoff; on success, `status` becomes `delivered`.
4. Outbound URLs are validated to reject private / link-local / loopback addresses (SSRF protection).

### Persistence model for notebook pages

Notebook pages are edited locally in TipTap and persisted via debounced `PATCH /pages/{id}` with the full markdown body. Last-write-wins. No WebSocket, no CRDT.

### No background loops

The backend runs no long-lived async tasks. Side-effects live in fire-and-forget `asyncio.create_task` calls on the request path:

- **Embedding generation** — triggered on page / row / event write.
- **Wiki link extraction** — triggered on page write.
- **Webhook delivery** — triggered on the originating event; retries are scheduled inline.

Heavier inference (curation, universal search) runs client-side in the Claude plugin, which POSTs results back via REST.

## Migrations

Schema is managed with Alembic (`backend/migrations/`, config at `alembic.ini`). `init_db` runs migrations to head on startup. Each migration is a reversible `upgrade()` / `downgrade()` pair using raw SQL via `op.execute`.

## Frontend architecture

Next.js 16 (App Router) with Tailwind 4.

```
frontend/src/
├── app/
│   ├── page.tsx              # Home / landing
│   ├── login/                # Register + password login
│   ├── join/[code]/          # Accept workspace invite
│   ├── workspaces/
│   │   └── [workspaceId]/    # Workspace dashboard
│   ├── notebooks/            # Wiki notebook editor (TipTap)
│   ├── memory/               # History browser ([storeId] detail)
│   ├── rooms/                # Chat rooms (REST-polled)
│   ├── tables/               # Table editor
│   ├── files/                # File uploads
│   ├── search/               # Universal search
│   └── docs/                 # In-app documentation
├── components/               # Shared React components
└── lib/
    └── api.ts                # HTTP client (fetch wrapper)
```

## Client surface

### CLI (`cli/`)

A Python CLI intended to be driven by coding agents running alongside Stash (e.g. Claude Code via the plugin below). Exposes auth, workspaces, notebooks, history push / query / search, tables, and files over REST. Humans can run it too, but the primary consumer is the agent.

### Claude plugin (`plugins/claude-plugin/`)

A plugin loaded by Claude Code. Two integration paths into the backend:

- `hooks/hooks.json` registers Claude Code lifecycle hooks (SessionStart, UserPromptSubmit, PostToolUse, Stop, SessionEnd). The handlers in `scripts/` push events and inject context via the lightweight `stash_client.py` HTTP client — direct REST, no CLI in the loop.
- `skills/` ships slash-command skills (`/stash:connect`, `/search`, `/sleep`, …). These are `SKILL.md` prompt templates that shell out to the `stash` CLI; they do not call REST directly.
- `CLAUDE.md` teaches the agent the CLI exists and documents the relevant commands so the agent uses it unprompted.

The backend serves the skill manifest at `GET /skill/stash/SKILL.md` for plugin bootstrap.

## Deployment

### Local development

```
./start.sh
```

Runs Postgres via docker compose, then uvicorn on `:3456` and `next dev` on `:3457`.

### Self-hosted (docker compose)

```
docker compose up -d
```

Three containers: `postgres` (pgvector/pg16), `backend` (uvicorn), `frontend` (Next.js). See `docker-compose.yml`.

### Production

`docker-compose.prod.yml` plus `Caddyfile` add a Caddy reverse proxy in front of the backend + frontend, handling TLS and routing.

### Required

- PostgreSQL 16+ with pgvector extension

### Optional

- **S3-compatible storage** — file uploads (falls back to local disk)
- **Embedding provider** — for semantic search (OpenAI, Hugging Face, local sentence-transformers, or BYO)
- **RAGflow** — document ingestion (`workspaces.ragflow_dataset_id`, `documents.ragflow_doc_id`)
