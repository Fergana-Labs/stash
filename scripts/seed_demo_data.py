"""Seed realistic demo data for dashboard visualizations.

Run:  python3.13 scripts/seed_demo_data.py
"""

import asyncio
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
import numpy as np

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://stash:stash@localhost:5432/stash"
)

SAM_ID = UUID("fc4d8f89-8d5f-41d6-91b8-5a8c965bbac0")
HENRY_ID = UUID("a0000000-0000-0000-0000-000000000099")
WORKSPACE_ID = UUID("b0000000-0000-0000-0000-000000000001")

# Existing notebook IDs
NB_ARCH = UUID("c0000000-0000-0000-0000-000000000001")
NB_RESEARCH = UUID("c0000000-0000-0000-0000-000000000002")
NB_MEETINGS = UUID("c0000000-0000-0000-0000-000000000003")

EMBEDDING_DIM = 384

NOW = datetime.now(timezone.utc)


def random_embedding():
    """Generate a random unit embedding vector."""
    v = np.random.randn(EMBEDDING_DIM).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def cluster_embedding(center_idx: int, noise: float = 0.3):
    """Generate an embedding near one of several cluster centers."""
    rng = np.random.default_rng(center_idx * 1000 + random.randint(0, 999))
    center = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    center /= np.linalg.norm(center)
    v = center + np.random.randn(EMBEDDING_DIM).astype(np.float32) * noise
    v /= np.linalg.norm(v)
    return v


# ---------------------------------------------------------------------------
# Notebook pages to add (varied topics, different lengths, wiki links)
# ---------------------------------------------------------------------------
NEW_PAGES = [
    # Architecture Notes notebook
    (NB_ARCH, "WebSocket Gateway", """# WebSocket Gateway Architecture

Our real-time communication layer uses a WebSocket gateway built on top of FastAPI
and the `websockets` library. Each workspace gets its own channel multiplexer.

## Connection Lifecycle

1. Client connects with JWT token
2. Gateway validates and assigns to workspace channel
3. Messages are broadcast via Redis pub/sub
4. Heartbeat every 30s keeps connection alive

## Scaling Strategy

For horizontal scaling we use Redis as the message broker between gateway instances.
Each instance subscribes to workspace channels and forwards messages to local clients.

See also: [[CRDT Strategy]], [[Load Balancer Config]]
""", SAM_ID, 2),
    (NB_ARCH, "Load Balancer Config", """# Load Balancer Configuration

We use Caddy as our reverse proxy with automatic HTTPS.

## Routing Rules

- `/api/*` → backend (port 3456)
- `/ws/*` → websocket gateway (port 3457)
- `/*` → frontend (port 3000)

## Health Checks

Caddy performs health checks every 10s. If a backend instance fails 3 consecutive
checks, it's removed from the pool.

## Rate Limiting

Rate limiting is handled at the application level via slowapi, not at the
load balancer. This gives us per-user granularity.

See also: [[WebSocket Gateway]], [[Deployment Pipeline]]
""", SAM_ID, 3),
    (NB_ARCH, "Deployment Pipeline", """# Deployment Pipeline

## CI/CD Flow

1. Push to `main` triggers GitHub Actions
2. Run tests (pytest + vitest)
3. Build Docker images
4. Push to container registry
5. Deploy to Render via webhook

## Database Migrations

Alembic migrations run automatically on startup. The backend checks for pending
migrations and applies them before accepting traffic.

## Rollback Procedure

If a deployment fails health checks:
1. Render automatically rolls back to previous deploy
2. Alert fires in Slack #incidents channel
3. On-call engineer investigates

See also: [[Load Balancer Config]], [[Monitoring Setup]]
""", SAM_ID, 5),
    (NB_ARCH, "Monitoring Setup", """# Monitoring and Observability

## Logging

Structured JSON logs via Python's `logging` module. Every request gets a
correlation ID that propagates through the entire call chain.

## Metrics

Key metrics we track:
- Request latency (p50, p95, p99)
- WebSocket connection count
- Database query duration
- Embedding generation throughput
- Cache hit rates

## Alerting

Alerts fire when:
- p99 latency exceeds 2s for 5 minutes
- Error rate exceeds 1% for 3 minutes
- Database connection pool is >80% utilized

See also: [[Deployment Pipeline]]
""", HENRY_ID, 4),
    (NB_ARCH, "Database Schema Design", """# Database Schema Design

## Core Tables

### Users
Simple user table with bcrypt password hashes and API key authentication.
Each user gets a unique `mc_` prefixed API key.

### Workspaces
Workspaces are the top-level organizational unit. Each workspace has an
invite code for easy sharing.

### Notebooks & Pages
Notebooks contain pages. Pages store markdown content and maintain
tsvector indexes for full-text search. Embeddings are computed async.

## Indexing Strategy

- GIN indexes on tsvector columns for search
- B-tree indexes on foreign keys
- pgvector ivfflat index on embedding columns (lists=100)

## Connection Pooling

We use asyncpg with a pool of 5-20 connections. The pool auto-scales
based on demand.

See also: [[Embedding Pipeline]], [[CRDT Strategy]]
""", SAM_ID, 1),
    (NB_ARCH, "Authentication Flow", """# Authentication System

## API Key Authentication

Every authenticated request requires a Bearer token in the format `mc_<random>`.
The key is SHA-256 hashed and compared against the stored hash.

## Password Login

Users can also log in with username + password. Passwords are hashed with
bcrypt (12 rounds). On successful login, a new API key is generated.

## Session Management

API keys don't expire. Users can rotate their key by logging in again,
which generates a new key and invalidates the old one.

## Authorization

Access control is workspace-based:
- Workspace members can read/write all resources in the workspace
- Personal resources (no workspace_id) are private to the creator
- Admins can manage workspace membership

See also: [[Database Schema Design]]
""", HENRY_ID, 6),

    # Research Papers notebook
    (NB_RESEARCH, "RLHF Overview", """# Reinforcement Learning from Human Feedback

## Key Insight

RLHF trains a reward model from human preference data, then uses that reward
model to fine-tune a language model via PPO (Proximal Policy Optimization).

## Three-Phase Training

1. **Supervised Fine-Tuning (SFT)**: Train on high-quality demonstrations
2. **Reward Model Training**: Learn human preferences from comparison data
3. **PPO Optimization**: Optimize the policy against the reward model

## Challenges

- Reward hacking: the model finds exploits in the reward model
- Distribution shift: the policy drifts from the SFT distribution
- Scalable oversight: hard to get reliable human feedback on complex tasks

## Papers

- InstructGPT (Ouyang et al., 2022)
- Training language models to follow instructions (Anthropic, 2022)

See also: [[Constitutional AI]], [[Scaling Laws]]
""", SAM_ID, 8),
    (NB_RESEARCH, "Retrieval Augmented Generation", """# RAG: Retrieval Augmented Generation

## Architecture

RAG combines a retriever (typically dense passage retrieval) with a generator
(language model). The retriever finds relevant documents, which are prepended
to the prompt as context.

## Our Implementation

1. Content is chunked into ~512 token segments
2. Each chunk is embedded using our embedding pipeline
3. At query time, we embed the query and find top-k nearest neighbors
4. Retrieved chunks are formatted as context for the LLM

## Chunking Strategy

We use recursive character splitting with:
- Chunk size: 512 tokens
- Overlap: 64 tokens
- Split on paragraph > sentence > word boundaries

## Evaluation

We measure retrieval quality via:
- Recall@k for different k values
- MRR (Mean Reciprocal Rank)
- End-to-end answer quality via human eval

See also: [[Embedding Pipeline]], [[Attention Is All You Need]]
""", SAM_ID, 10),
    (NB_RESEARCH, "Mixture of Experts", """# Mixture of Experts (MoE)

## Core Concept

MoE models use a gating network to route each token to a subset of expert
networks. This allows scaling model parameters without proportionally
scaling compute.

## Architecture

- **Gate**: Learned routing function (typically top-k softmax)
- **Experts**: Independent feed-forward networks
- **Load Balancing**: Auxiliary loss to prevent expert collapse

## Key Results

- Switch Transformer: simplified MoE with top-1 routing
- GShard: scales to 600B parameters across TPU pods
- Mixtral 8x7B: open-source MoE achieving strong results

## Relevance to Our System

Understanding MoE helps us reason about model behavior when using
different model sizes for different tasks (routing to cheap vs expensive).

See also: [[Scaling Laws]], [[RLHF Overview]]
""", HENRY_ID, 7),
    (NB_RESEARCH, "Vector Database Comparison", """# Vector Database Comparison

## Options Evaluated

### pgvector (our choice)
- Pros: lives in Postgres, no extra infrastructure, ACID transactions
- Cons: slower than purpose-built solutions at scale
- Performance: <50ms for 100k vectors with ivfflat

### Pinecone
- Pros: managed service, fast, good filtering
- Cons: vendor lock-in, cost at scale

### Weaviate
- Pros: open-source, hybrid search, good API
- Cons: requires separate infrastructure

### Qdrant
- Pros: fast, Rust-based, good filtering
- Cons: less mature ecosystem

## Decision

pgvector wins for our scale (<1M vectors). The operational simplicity of
keeping everything in Postgres outweighs the performance benefits of a
dedicated vector store.

See also: [[Embedding Pipeline]], [[Database Schema Design]]
""", SAM_ID, 9),
    (NB_RESEARCH, "Prompt Engineering Patterns", """# Prompt Engineering Patterns

## Chain of Thought (CoT)

Asking the model to "think step by step" before answering improves
accuracy on reasoning tasks by 20-40%.

## Few-Shot Examples

Providing 3-5 examples in the prompt helps the model understand the
expected format and behavior.

## System Prompts

System prompts set the context and constraints. Key principles:
- Be specific about the role
- Define output format explicitly
- Include negative examples ("don't do X")

## Tool Use

Structured tool calling lets the model invoke functions:
1. Define tool schemas with JSON Schema
2. Model decides when to call tools
3. Results are fed back as tool results

## Evaluation

We use a combination of:
- Automated metrics (BLEU, ROUGE for summarization)
- LLM-as-judge for open-ended quality
- Human evaluation for critical flows

See also: [[RLHF Overview]], [[Constitutional AI]]
""", HENRY_ID, 11),

    # Meeting Notes notebook
    (NB_MEETINGS, "Sprint Planning - Week 16", """# Sprint Planning - Week 16

**Date:** 2026-04-14
**Attendees:** Sam, Henry

## Goals

1. Ship dashboard visualizations v1
2. Fix WebSocket reconnection bug
3. Add table column reordering

## Assignments

### Sam
- 3D embedding space explorer
- Fix tooltip overflow on dashboard cards
- Knowledge density improvements

### Henry
- WebSocket reconnection with exponential backoff
- Table column drag-and-drop
- Write E2E tests for notebook editor

## Blockers

- Need to decide on vector search pagination strategy
- Waiting on Render support ticket for custom domains
""", SAM_ID, 0),
    (NB_MEETINGS, "Architecture Review - Q2", """# Architecture Review - Q2 2026

**Date:** 2026-04-10
**Attendees:** Sam, Henry

## What's Working

- pgvector performance is solid at our scale
- CRDT-based collaboration is stable
- Embedding pipeline throughput is good

## Concerns

- Single Postgres instance is a scaling bottleneck
- No read replicas yet
- Alembic migration chain is fragile (missing files)
- Frontend bundle size growing (now 450KB gzipped)

## Action Items

1. Set up Postgres read replica for analytics queries
2. Investigate connection pooling with PgBouncer
3. Audit and fix migration chain
4. Code-split dashboard visualizations

## Next Review

Scheduled for Q3 start (July 2026)
""", SAM_ID, 3),
    (NB_MEETINGS, "Design Review - Dashboard", """# Design Review - Dashboard Visualizations

**Date:** 2026-04-12
**Attendees:** Sam, Henry

## Components Reviewed

### Agent Activity Timeline
- Heat grid looks good
- Need more left margin for agent names
- Consider adding date labels on x-axis

### Knowledge Density Map
- Treemap layout needs work — too many equal-sized rectangles
- Stem labels are ugly (e.g., "Architectur")
- Filter out noise words from table column names

### Embedding Space
- 2D projection is too flat
- Switch to 3D PCA with rotation
- Add depth cues (size/opacity)

### Page Graph
- Physics simulation too jittery for hover
- Auto-select first notebook
- Remove extra "View" button

## Follow-up

Sam to implement all fixes this sprint.
""", SAM_ID, 1),
    (NB_MEETINGS, "Onboarding Notes - Henry", """# Onboarding Notes - Henry

**Date:** 2026-04-14

## Environment Setup

1. Clone repo, install Python 3.13 + Node 20
2. Create Postgres database: `stash`
3. Copy `.env.example` to `.env`
4. Run `python3.13 -m pip install -r backend/requirements.txt`
5. Run `cd frontend && npm install`
6. Start with `./start.sh`

## Architecture Overview

- Backend: FastAPI + asyncpg + pgvector
- Frontend: Next.js 16 + Tailwind CSS v4
- Real-time: WebSocket with Yjs CRDT
- Auth: API key (mc_ prefix) + bcrypt passwords

## Key Files

- `backend/main.py` — app entry point with lifespan
- `backend/database.py` — asyncpg pool + Alembic
- `frontend/src/app/workspaces/[workspaceId]/page.tsx` — main dashboard
- `frontend/src/components/viz/` — visualization components
""", HENRY_ID, 2),
    (NB_MEETINGS, "Incident Report - 2026-04-08", """# Incident Report: Database Connection Exhaustion

**Date:** 2026-04-08
**Duration:** 45 minutes
**Severity:** P1

## Timeline

- 14:15 UTC — Alert fires: DB pool at 100% utilization
- 14:20 UTC — On-call (Sam) acknowledges
- 14:25 UTC — Root cause identified: embedding pipeline holding connections
- 14:30 UTC — Hotfix deployed: added connection timeout to pipeline
- 15:00 UTC — Pool utilization back to normal

## Root Cause

The embedding pipeline was fetching all pages in a single transaction,
holding a connection for the entire batch. With 200+ pages, this took
several minutes, exhausting the pool.

## Fix

- Added `statement_timeout` to embedding queries
- Process pages in batches of 20
- Added connection pool metrics to monitoring dashboard

## Prevention

- Set max query duration to 30s at pool level
- Add circuit breaker for batch operations
- Better pool utilization alerting (alert at 70%, not 90%)

See also: [[Monitoring Setup]], [[Embedding Pipeline]]
""", SAM_ID, 5),
]

# ---------------------------------------------------------------------------
# History events (agent activity — spread across last 30 days)
# ---------------------------------------------------------------------------
AGENTS = ["claude-opus", "claude-sonnet", "cursor-agent", "github-copilot", "custom-bot"]
EVENT_TYPES = ["message", "tool_call", "edit", "search", "embedding", "error"]

def generate_history_events(count: int = 200):
    """Generate realistic agent activity events spread over 30 days."""
    events = []
    for _ in range(count):
        agent = random.choice(AGENTS)
        event_type = random.choice(EVENT_TYPES)
        # Cluster activity in business hours, with more recent days busier
        days_ago = random.betavariate(2, 5) * 30
        hour = random.gauss(14, 3)  # Peak at 2 PM
        hour = max(8, min(22, hour))
        ts = NOW - timedelta(days=days_ago, hours=24 - hour)
        user = random.choice([SAM_ID, HENRY_ID])

        content_templates = {
            "message": f"Discussed {random.choice(['architecture', 'deployment', 'testing', 'performance', 'security'])} with user",
            "tool_call": f"Called {random.choice(['read_file', 'edit_file', 'search', 'run_tests', 'git_diff', 'list_files'])}",
            "edit": f"Edited {random.choice(['backend/main.py', 'frontend/src/app/page.tsx', 'backend/services/analytics_service.py', 'frontend/src/components/viz/EmbeddingSpaceExplorer.tsx'])}",
            "search": f"Searched for {random.choice(['embedding', 'websocket', 'authentication', 'migration', 'CRDT', 'treemap'])}",
            "embedding": f"Generated embeddings for {random.randint(1, 50)} documents",
            "error": f"Error: {random.choice(['timeout', 'connection refused', 'rate limited', 'invalid token', 'not found'])}",
        }

        events.append({
            "id": uuid4(),
            "workspace_id": WORKSPACE_ID if random.random() > 0.2 else None,
            "tag_name": agent,
            "event_type": event_type,
            "session_id": f"session-{random.randint(1, 30):03d}",
            "content": content_templates[event_type],
            "metadata": {},
            "created_by": user,
            "created_at": ts,
            "embedding": cluster_embedding(AGENTS.index(agent)),
        })
    return events


# ---------------------------------------------------------------------------
# Table rows for Model Comparison table
# ---------------------------------------------------------------------------
TABLE_ID = UUID("70000000-0000-0000-0000-000000000001")

NEW_TABLE_ROWS = [
    {"model": "GPT-4o", "provider": "OpenAI", "context_window": 128000, "cost_per_mtok": 5.0, "speed": "fast", "quality": "high", "release_date": "2024-05-13"},
    {"model": "Claude Opus 4", "provider": "Anthropic", "context_window": 200000, "cost_per_mtok": 15.0, "speed": "medium", "quality": "very high", "release_date": "2025-05-22"},
    {"model": "Claude Sonnet 4", "provider": "Anthropic", "context_window": 200000, "cost_per_mtok": 3.0, "speed": "fast", "quality": "high", "release_date": "2025-05-22"},
    {"model": "Gemini 2.5 Pro", "provider": "Google", "context_window": 1000000, "cost_per_mtok": 1.25, "speed": "fast", "quality": "high", "release_date": "2025-03-25"},
    {"model": "Llama 3.1 405B", "provider": "Meta", "context_window": 128000, "cost_per_mtok": 0.0, "speed": "slow", "quality": "high", "release_date": "2024-07-23"},
    {"model": "Mistral Large", "provider": "Mistral", "context_window": 128000, "cost_per_mtok": 2.0, "speed": "fast", "quality": "medium-high", "release_date": "2024-02-26"},
    {"model": "Deepseek V3", "provider": "DeepSeek", "context_window": 128000, "cost_per_mtok": 0.27, "speed": "medium", "quality": "high", "release_date": "2024-12-26"},
    {"model": "Grok 3", "provider": "xAI", "context_window": 131072, "cost_per_mtok": 3.0, "speed": "fast", "quality": "high", "release_date": "2025-02-17"},
    {"model": "Command R+", "provider": "Cohere", "context_window": 128000, "cost_per_mtok": 2.5, "speed": "medium", "quality": "medium", "release_date": "2024-04-04"},
    {"model": "Qwen 2.5 72B", "provider": "Alibaba", "context_window": 131072, "cost_per_mtok": 0.0, "speed": "medium", "quality": "medium-high", "release_date": "2024-09-19"},
]


async def main():
    from pgvector.asyncpg import register_vector

    conn = await asyncpg.connect(DATABASE_URL)
    await register_vector(conn)
    try:
        print("Seeding demo data...")

        # -----------------------------------------------------------
        # 1. Add new notebook pages
        # -----------------------------------------------------------
        existing = {r["name"] for r in await conn.fetch(
            "SELECT name FROM notebook_pages WHERE notebook_id = ANY($1)",
            [NB_ARCH, NB_RESEARCH, NB_MEETINGS],
        )}

        pages_added = 0
        for nb_id, name, content, author, days_ago in NEW_PAGES:
            if name in existing:
                continue
            ts = NOW - timedelta(days=days_ago, hours=random.randint(0, 12))
            emb = cluster_embedding(hash(name) % 10)
            await conn.execute(
                """INSERT INTO notebook_pages (id, notebook_id, name, content_markdown, created_by, updated_by, created_at, updated_at, embedding)
                   VALUES ($1, $2, $3, $4, $5, $5, $6, $6, $7)""",
                uuid4(), nb_id, name, content, author, ts, emb,
            )
            pages_added += 1
        print(f"  Added {pages_added} notebook pages")

        # -----------------------------------------------------------
        # 2. Add history events
        # -----------------------------------------------------------
        existing_count = await conn.fetchval("SELECT COUNT(*) FROM history_events")
        if existing_count < 50:
            events = generate_history_events(200)
            for ev in events:
                await conn.execute(
                    """INSERT INTO history_events (id, workspace_id, tag_name, event_type, session_id, content, metadata, created_by, created_at, embedding)
                       VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)""",
                    ev["id"], ev["workspace_id"], ev["tag_name"], ev["event_type"],
                    ev["session_id"], ev["content"], "{}", ev["created_by"],
                    ev["created_at"], ev["embedding"],
                )
            print(f"  Added {len(events)} history events")
        else:
            print(f"  Skipped history events (already {existing_count})")

        # -----------------------------------------------------------
        # 3. Add table rows
        # -----------------------------------------------------------
        existing_rows = await conn.fetchval(
            "SELECT COUNT(*) FROM table_rows WHERE table_id = $1", TABLE_ID,
        )
        if existing_rows < 8:
            # Clear existing rows and re-seed with better data
            await conn.execute("DELETE FROM table_rows WHERE table_id = $1", TABLE_ID)
            for i, row_data in enumerate(NEW_TABLE_ROWS):
                import json
                emb = cluster_embedding(hash(row_data["model"]) % 10)
                await conn.execute(
                    """INSERT INTO table_rows (id, table_id, data, row_order, created_by, created_at, updated_at, embedding)
                       VALUES ($1, $2, $3::jsonb, $4, $5, $6, $6, $7)""",
                    uuid4(), TABLE_ID, json.dumps(row_data), i, SAM_ID,
                    NOW - timedelta(days=random.randint(0, 14)), emb,
                )
            print(f"  Added {len(NEW_TABLE_ROWS)} table rows")
        else:
            print(f"  Skipped table rows (already {existing_rows})")

        # -----------------------------------------------------------
        # 4. Ensure all existing pages have embeddings
        # -----------------------------------------------------------
        missing = await conn.fetch(
            "SELECT id FROM notebook_pages WHERE embedding IS NULL"
        )
        for r in missing:
            emb = random_embedding()
            await conn.execute(
                "UPDATE notebook_pages SET embedding = $1 WHERE id = $2",
                emb, r["id"],
            )
        print(f"  Backfilled {len(missing)} page embeddings")

        # -----------------------------------------------------------
        # 5. Clear caches so new data shows up
        # -----------------------------------------------------------
        await conn.execute(
            "DELETE FROM embedding_projections WHERE user_id = $1", SAM_ID,
        )
        print("  Cleared embedding projection cache")

        print("Done!")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
