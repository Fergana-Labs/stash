# Boozle

The auto-curating knowledge base for AI-augmented teams.

Throw in your bookmarks, Claude Code sessions, PDFs, YouTube videos, articles. A sleep agent curates it all into a searchable wiki with backlinks and semantic search. You never write wiki entries manually.

## Quickstart

```bash
pip install boozle
boozle register yourname
boozle import-bookmarks ~/Downloads/bookmarks.html
```

Your bookmarks are now being scraped, stored, and embedded. The sleep agent curates them into a wiki overnight.

```bash
boozle search "that article about transformer architectures"
```

## What it does

1. **Import bookmarks** — Export from Chrome/Firefox, run `boozle import-bookmarks`. Web articles get extracted as markdown. YouTube videos get transcripts. PDFs get parsed.

2. **Auto-curate** — A sleep agent runs periodically, reads everything you've ingested, and maintains a living wiki. Pattern cards, concept summaries, linked knowledge. You never touch it.

3. **Search everything** — `boozle search` uses AI to synthesize answers across all your data: notebooks, history, tables, documents.

4. **Wiki links** — Pages link to each other with `[[Page Name]]` syntax. Backlinks, page graph visualization, semantic search across all pages.

5. **Connect Claude Code** — Every AI session becomes searchable knowledge. Via MCP tools or CLI hooks, conversations accumulate instead of evaporating.

## Connect Claude Code

Add Boozle as an MCP server so Claude Code can read and write to your knowledge base:

```bash
claude mcp add boozle -- boozle mcp
```

Or set the environment variables:

```bash
export BOOZLE_API_KEY=your_api_key
export BOOZLE_URL=https://getboozle.com
```

## CLI Commands

```
boozle register <name>                  # Create account
boozle login <name>                     # Login with password
boozle auth <url> --api-key <key>       # Auth with API key

boozle import-bookmarks <file.html>     # Import Chrome/Firefox bookmarks
  --notebook "My Research"              #   Notebook name (default: "Bookmarks")
  --skip-scrape                         #   Import titles + URLs only (fast)
  --dry-run                             #   Preview without importing

boozle search <query>                   # Search across all knowledge
  --ws <workspace_id>                   #   Scope to a workspace
  --types history,notebook,table        #   Filter by resource type

boozle notebooks list                   # List notebooks
boozle notebooks add-page <nb> <name>   # Create a page
boozle history push <content>           # Log an event
boozle history search <query>           # Search history
```

## Features

- **Bookmark import** with web scraping, YouTube transcript download, PDF parsing
- **Auto-curation** via configurable sleep agent (sources, interval, model)
- **Wiki-style notebooks** with `[[backlinks]]`, page graph, auto-index
- **Semantic search** across notebooks, tables, history (pgvector + OpenAI embeddings)
- **Universal search** with AI-powered synthesis across all resource types
- **Structured tables** with typed columns, filters, views, CSV import/export, row embeddings
- **File uploads** to S3-compatible storage (Cloudflare R2, AWS S3, MinIO)
- **Real-time collaboration** on notebook pages (Yjs + WebSocket)
- **20+ MCP tools** for AI agent integration
- **Webhooks** for event-driven pipelines
- **REST API** for everything

## Hosted

Use [getboozle.com](https://getboozle.com) for free. No setup required.

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

Requires PostgreSQL with pgvector. Optional: S3-compatible storage, OpenAI API key (embeddings), Anthropic API key (sleep agent + universal search).

## Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL, pgvector
- **Frontend:** Next.js 16, React 19, TipTap, Yjs
- **CLI:** Python, Typer
- **Real-time:** WebSocket, SSE
- **Search:** Full-text (PostgreSQL), semantic (pgvector + OpenAI), AI synthesis (Anthropic)

## License

MIT
