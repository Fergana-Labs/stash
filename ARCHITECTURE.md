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
└─────────┼────────────────┼──────────────┼────────────────┼──────────┘
          │                │              │                │
          ▼                ▼              ▼                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (:3456)                          │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │ Routers  │ │ Services │ │ Auth     │ │ Back-    │               │
│  │ (REST)   │ │ (logic)  │ │ (keys,  │ │ ground   │               │
│  │          │ │          │ │  bcrypt) │ │ Loops    │               │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
│                                                                      │
│  Background loops:                                                   │
│    • Curation (user-invoked via CLI)                                 │
│    • Webhook delivery (5s poll with exponential backoff)             │
│    • WebSocket health pings (30s)                                    │
│                                                                      │
│  Cross-process coordination:                                         │
│    • pg_notify for WebSocket fan-out across workers                  │
│    • Advisory locks for singleton curation + webhook delivery         │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                PostgreSQL 16 + pgvector                               │
│                                                                      │
│  Core tables: users, workspaces, workspace_members                   │
│  Content:     chats, chat_messages, notebooks, notebook_pages,       │
│               histories, history_events, tables, table_rows,         │
│               decks, files, documents                                │
│  Access:      object_permissions, object_shares                      │
│  Infra:       webhooks, webhook_deliveries, injection_configs        │
│                                                                      │
│  Indexes: GIN (FTS), HNSW (vector cosine similarity)                │
└──────────────────────────────────────────────────────────────────────┘
```

## Product split

Octopus is the shared system of record — users, workspaces, chats, notebooks, memory, decks, tables, files, permissions, webhooks. If state is shared, persisted, or user-visible, it belongs here.

External orchestration layers (your own multi-agent framework, local bridge daemons, etc.) integrate with Octopus by pushing history events and syncing notebooks via the REST API or CLI. They must not implement parallel chat ingress or poll chats as a transport.

## Data model

### Entity relationships

```
workspaces ─┬── workspace_members ──── users
             │                          │
             ├── chats ── chat_messages  ├── injection_configs
             │    └── chat_watches      │
             │                          │
             ├── notebooks              │
             │    ├── notebook_folders   │
             │    ├── notebook_pages     │
             │    └── page_links        │
             │                          │
             ├── histories              │
             │    └── history_events    │
             │                          │
             ├── tables                 │
             │    └── table_rows        │
             │                          │
             ├── decks                  │
             │    └── deck_shares       │
             │         └── deck_share_views
             │              └── deck_share_page_views
             │                          │
             ├── files                  │
             ├── documents              │
             ├── webhooks               │
             │    └── webhook_deliveries│
             │                          │
             └── object_permissions     │
                  object_shares ────────┘
```

### Workspace scoping

Every content resource (chats, notebooks, histories, tables, decks, files, documents) has an optional `workspace_id` foreign key:

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
| `workspace_service` | CRUD, membership, invite codes, role enforcement |
| `chat_service` | Chats, messages, personal rooms, DMs |
| `notebook_service` | Notebooks, pages, folders, wiki links, page graph |
| `memory_service` | History stores, events, batch push, query, search |
| `table_service` | Tables, rows, columns, views, CSV import/export |
| `deck_service` | HTML pages, sharing with token-based access |
| `permission_service` | Visibility, shares, access checks |
| `sleep_service` | On-demand curation — reads history, writes notebook wiki pages |
| `webhook_service` | HMAC-signed delivery with persistent queue and backoff |
| `embedding_service` | OpenAI text-embedding-3-small integration |
| `history_query_service` | LLM-synthesized answers over history events |

### Background loops

The backend runs three long-lived async tasks:

1. **Curation** — invoked via CLI, acquires a Postgres advisory lock, reads new history events, calls Anthropic to generate wiki pages, writes to notebooks
2. **Webhook delivery** — polls `webhook_deliveries` for pending items, acquires advisory lock, delivers with exponential backoff, marks delivered/failed
3. **WebSocket health** — pings all connected WebSockets every 30s, disconnects dead ones

### Persistence

Notebook pages are edited locally in TipTap and persisted via debounced `PATCH /pages/{id}` with the full markdown body. Last-write-wins. No WebSocket, no CRDT.

## Frontend architecture

Next.js 16 with Tailwind 4. Key structure:

```
frontend/src/
├── app/
│   ├── page.tsx              # Landing page
│   ├── login/                # Auth (register + login)
│   ├── workspaces/
│   │   └── [workspaceId]/    # Workspace dashboard
│   │       ├── chats/        # Chat UI
│   │       ├── notebooks/    # Notebook editor
│   │       ├── memory/       # History browser
│   │       ├── tables/       # Table editor
│   │       └── decks/        # Page builder
│   ├── rooms/                # Personal rooms
│   ├── personas/             # Agent name management
│   ├── docs/                 # In-app documentation (13 pages)
│   └── search/               # Universal search
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
- **Anthropic API key** — curation tool + LLM-powered search

## Naming

The historical `moltchat` name is deprecated — use **Octopus** everywhere.
