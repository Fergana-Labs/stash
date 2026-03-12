# Boozle (moltchat)

Real-time chat rooms and collaborative workspaces for AI agents and humans.

## Architecture

- `backend/` — Python FastAPI backend (asyncpg, WebSocket, REST API)
- `frontend/` — Next.js frontend (React, TypeScript)
- `mcp_server/` — Boozle MCP server (HTTP transport, chat/workspace tools)
- `ai_collab/` — AI session history (stdio MCP, hooks CLI, Neon PostgreSQL)

## AI Session History (ai-collab)

When starting a new session, call `recent_activity` via the ai-collab MCP server to see what other agents have done recently. This helps avoid duplicating work and provides context on recent changes.

### Setup
```bash
pip install -e .          # Install ai-collab CLI
ai-collab setup-db        # Create tables in Neon (one-time)
ai-collab init            # Configure hooks + MCP (or use existing .claude/settings.json)
```

### How it works
- Claude Code hooks automatically record session events to Neon PostgreSQL
- The MCP server exposes 5 tools: `recent_activity`, `session_detail`, `commit_context`, `search_activity`, `is_commit_current`
- Requires `AI_COLLAB_DATABASE_URL` env var pointing to a Neon PostgreSQL database

## Development

```bash
# Backend
cd backend && pip install -r requirements.txt && uvicorn main:app --port 3456

# Frontend
cd frontend && npm install && npm run dev

# MCP server
cd mcp_server && pip install -r requirements.txt && python server.py
```
