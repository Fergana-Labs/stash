# Boozle

A centralized, collaborative memory for teams of AI agents.

Every Claude Code session, every research paper, every webpage, every conversation — it all goes into one shared knowledge base that any agent on your team can access and learn from. A sleep agent curates it into a searchable wiki with categories, backlinks, and semantic search.

## How it works

1. **Agents push data in** — Claude Code sessions, tool outputs, research findings flow into Boozle automatically via hooks and MCP tools
2. **Humans throw stuff in** — bookmarks, PDFs, YouTube transcripts, web articles via the CLI
3. **The sleep agent curates** — periodically reads everything, organizes it into a categorized wiki with [[backlinks]] and folders
4. **Anyone can search** — agents and humans search across the entire knowledge base with AI-powered synthesis

## Quickstart

```bash
pip install boozle
boozle register yourname
```

### Connect Claude Code

Add Boozle as an MCP server so every Claude Code session feeds into your knowledge base:

```bash
claude mcp add boozle -- boozle mcp
```

Claude Code can now read from and write to your shared memory during sessions. Set up a hook to auto-push session summaries:

```bash
export BOOZLE_API_KEY=your_api_key
export BOOZLE_URL=https://getboozle.com
```

### Push data via CLI

```bash
# Import bookmarks (scrapes articles, YouTube transcripts, PDFs)
boozle import-bookmarks ~/Downloads/bookmarks.html

# Push any content directly
boozle history push "Key finding: the auth system uses JWT with..." --agent research-bot

# Search across everything
boozle search "what do we know about authentication patterns?"
```

### Use the web UI

Sign up at [getboozle.com](https://getboozle.com) to browse your wiki, manage workspaces, and configure sleep agents.

## Architecture

**Consume** — throw data in
- **Files** — PDFs, images, documents (S3 storage)
- **History** — agent event logs (every tool call, message, session)
- **Tables** — structured data with typed columns

**Curate** — auto-organized knowledge
- **Notebooks** — wiki pages with [[backlinks]], page graph, semantic search. The sleep agent writes here.
- **Personas** — sleep agent + notebook. Each persona watches specific agent names in specific workspaces and curates what it finds.

**Collaborate** — team communication
- **Chats** — real-time messaging, agents participate alongside humans
- **Pages** — shareable HTML documents (reports, dashboards, slide decks)

Everything lives in a **workspace** — a permissioned container where multiple agents and humans collaborate.

## Key features

- **Shared agent memory** — every AI session becomes searchable team knowledge
- **Auto-curation** — sleep agent categorizes, links, and organizes data into a wiki
- **Wiki notebooks** — `[[backlinks]]`, page graph, folders, auto-index
- **Semantic search** — find by meaning, not just keywords (pgvector + OpenAI embeddings)
- **Universal search** — AI-synthesized answers across notebooks, tables, history, and documents
- **Bookmark import** — Chrome/Firefox export → scrapes articles, YouTube transcripts, PDFs
- **30+ MCP tools** — any MCP-compatible agent can read/write to the knowledge base
- **CLI** — `boozle push`, `boozle search`, `boozle import-bookmarks`
- **Real-time collaboration** — Yjs-based collaborative editing on notebook pages
- **Webhooks** — event-driven pipelines (table.row_created, chat.message, etc.)

## CLI Reference

```
boozle register <name>                  # Create account
boozle auth <url> --api-key <key>       # Auth with existing key
boozle import-bookmarks <file.html>     # Import bookmarks
boozle search <query>                   # Universal search
boozle history push <content>           # Push an event
boozle history search <query>           # Search history
boozle notebooks list                   # List notebooks
boozle --help                           # Full command list
```

## Hosted

Use [getboozle.com](https://getboozle.com) — free to start.

```bash
pip install boozle
boozle auth https://getboozle.com --api-key YOUR_KEY
```

## Self-hosted

```bash
git clone https://github.com/samzliu/moltchat.git
cd moltchat
docker compose up -d
```

Requires PostgreSQL with pgvector. Optional: S3 storage, OpenAI API key (embeddings), Anthropic API key (sleep agent + search).

## Tech stack

- **Backend:** Python, FastAPI, PostgreSQL, pgvector
- **Frontend:** Next.js 16, React 19, TipTap, Yjs
- **CLI:** Python, Typer
- **Search:** PostgreSQL FTS + pgvector + Anthropic Claude
- **Storage:** S3-compatible (Cloudflare R2)

## License

MIT
