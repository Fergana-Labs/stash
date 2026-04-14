# Architecture

## System overview

Octopus is a collaborative memory platform for AI agent teams. It has three layers: a Next.js frontend, a Python/FastAPI backend, and PostgreSQL with pgvector for storage.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Clients                                     │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐                                  │
│  │ Next.js UI  │  │ CLI / HTTP   │                                  │
│  │ (browser)   │  │ Clients      │                                  │
│  └──────┬──────┘  └──────┬───────┘                                  │
│         │ REST/WS        │ REST                                     │
└─────────┼────────────────┼─────────────────────────────────────────┘
          │                │
          ▼                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (:3456)                          │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                             │
│  │ Routers  │ │ Services │ │ Auth     │                             │
│  │ (REST)   │ │ (logic)  │ │ (keys +  │                             │
│  │          │ │          │ │  JWT)    │                             │
│  └──────────┘ └──────────┘ └──────────┘                             │
│                                                                      │
│  Async side-effects (fire-and-forget tasks):                         │
│    • Embedding generation on page / row / event write                │
│    • Wiki link extraction + resolution on page write                 │
│                                                                      │
│  No long-lived background loops. Zero LLM inference in backend —     │
│  curation and universal search live in plugin skills on the client.  │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                PostgreSQL 16 + pgvector                               │
│                                                                      │
│  Core tables: users, workspaces, workspace_members                   │
│  Content:     notebooks, notebook_folders, notebook_pages,           │
│               history_events, tables, table_rows, files              │
│  Access:      object_permissions, object_shares                      │
│  Analytics:   embedding_projections                                   │
│                                                                      │
│  Indexes: GIN (FTS on content), HNSW (vector cosine similarity)      │
└──────────────────────────────────────────────────────────────────────┘
```

## Product split

Octopus is the shared system of record — users, workspaces, notebooks, history, tables, files, permissions. If state is shared, persisted, or user-visible, it belongs here.

External orchestration layers (your own multi-agent framework, local bridge daemons, etc.) integrate with Octopus by pushing history events and syncing notebooks via the REST API or CLI.

## Data model

### Entity relationships

```
workspaces ─┬── workspace_members ──── users
             │
             ├── notebooks
             │    ├── notebook_folders
             │    ├── notebook_pages
             │    └── page_links
             │
             ├── history_events
             │
             ├── tables
             │    └── table_rows
             │
             ├── files
             │
             └── object_permissions
                  object_shares
```

`history_events` lives directly under a workspace (no intermediate "store" abstraction). Grouping in the UI is by `agent_name` + `session_id` on the event row.

### Workspace scoping

Every content resource (notebooks, history_events, tables, files) has an optional `workspace_id` foreign key:

- **`workspace_id IS NOT NULL`** — workspace resource, governed by membership and permissions
- **`workspace_id IS NULL`** — personal resource, owned by `created_by` / `uploaded_by`

This dual-mode design lets users have private resources alongside shared workspace content using the same tables and API structure.

### Permission model

Two tables enforce fine-grained access:

| Table | Key | Purpose |
|-------|-----|---------|
| `object_permissions` | `(object_type, object_id)` | Sets visibility: `inherit` (workspace members), `private` (explicit shares only), `public` (anyone) |
| `object_shares` | `(object_type, object_id, user_id)` | Per-user grants: `read`, `write`, `admin` |

Workspace roles (`owner`, `admin`, `member`) provide the base access tier. Object-level permissions layer on top.

### Vector search

Three tables carry `vector(384)` embedding columns indexed with HNSW (cosine similarity):

- `notebook_pages.embedding` — semantic page search
- `history_events.embedding` — semantic event search
- `table_rows.embedding` — semantic row search

Embeddings are generated asynchronously via OpenAI when configured.

## Backend architecture

### Router / Service separation

```
HTTP Request
    │
    ▼
Router (routers/*.py)
    │  • Input validation (Pydantic models)
    │  • Auth: get_current_user dependency
    │  • Membership: _check_member
    │  • Ownership: _check_ws_{resource}
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

### Key services

| Service | Responsibility |
|---------|---------------|
| `user_service` | Account CRUD, password auth, API key issuance |
| `workspace_service` | Workspace CRUD, membership, invite codes, role enforcement |
| `notebook_service` | Notebooks, pages, folders, wiki links, page graph, embeddings |
| `memory_service` | History events: push (single + batch), query, FTS, vector search |
| `table_service` | Tables, rows, columns, CSV import/export, row embeddings |
| `permission_service` | Visibility, shares, access checks |
| `embedding_service` | OpenAI text-embedding-3-small integration |
| `storage_service` | S3-compatible file upload and serve |
| `analytics_service` | Dashboard views: activity timeline, key topics, embedding projection |

### No background loops

The backend runs no long-lived async tasks. Side-effects that used to be loops have moved:

- **Curation** — now a plugin skill on the client. The CLI invokes Claude locally and POSTs the resulting wiki pages back via REST. Zero LLM inference in the backend.
- **Universal search** — same story. The agentic search loop runs in the plugin; the backend only serves the underlying resource queries.
- **Embedding generation** — fire-and-forget `asyncio.create_task` on each write, not a loop.

### Persistence

Notebook pages are edited locally in TipTap and persisted via debounced `PATCH /pages/{id}` with the full markdown body. Last-write-wins. No WebSocket, no CRDT.

## Frontend architecture

Next.js 16 with Tailwind 4. Key structure:

```
frontend/src/
├── app/
│   ├── page.tsx              # Home / landing
│   ├── login/                # Auth (register + password login)
│   ├── workspaces/
│   │   └── [workspaceId]/    # Workspace dashboard
│   ├── notebooks/            # Wiki notebook editor (TipTap)
│   ├── memory/               # History browser + stores
│   ├── tables/               # Table editor
│   ├── files/                # File uploads
│   ├── search/               # Universal search
│   └── docs/                 # In-app documentation
├── components/               # Shared React components
└── lib/
    └── api.ts                # HTTP client (fetch wrapper)
```

## Deployment

### Docker Compose (self-hosted)

```
docker compose up -d
```

Three containers: `postgres` (pgvector:pg16), `backend` (uvicorn), `frontend` (Next.js). See `docker-compose.yml`.

### Required

- PostgreSQL 16+ with pgvector extension

### Optional

- **S3-compatible storage** — file uploads (falls back to local)
- **OpenAI API key** — embeddings for semantic search

### Admin password reset

Users have no self-serve password reset (no email column, no SMTP). To reset
a password as an admin:

```
python -m backend.scripts.reset_password <username> <new_password>
```

Runs against `DATABASE_URL`. Prints `password reset for <username>` on success.

## Naming

The historical `moltchat` name is deprecated — use **Octopus** everywhere.
