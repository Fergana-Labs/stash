# Boozle

A centralized, collaborative memory for teams of AI agents.

Every Claude Code session, every research paper, every webpage, every conversation — it all goes into one shared knowledge base that any agent on your team can access and learn from. A sleep agent curates it into a searchable wiki with categories, backlinks, and semantic search.

## Quickstart

### 1. Create an account

Go to [getboozle.com](https://getboozle.com) and register, or use the CLI:

```bash
pip install boozle
boozle register yourname
```

Copy your API key — you'll need it in the next step.

### 2. Connect Claude Code

```bash
# Connect to hosted Boozle (recommended)
claude mcp add --transport http boozle https://getboozle.com/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"
```

That's it. Claude Code can now read from and write to your shared knowledge base using 30+ MCP tools.

<details>
<summary>Alternative: run MCP server locally</summary>

```bash
claude mcp add \
  -e BOOZLE_API_KEY=YOUR_API_KEY \
  -e BOOZLE_URL=https://getboozle.com \
  boozle -- python -m mcp_server.server
```
</details>

### 3. Try it

Open Claude Code and paste these prompts:

**Push knowledge in:**
> "Search the web for the latest research on RAG architectures and save a summary to my Boozle knowledge base"

**Import your bookmarks:**
> "Run `boozle import-bookmarks ~/Downloads/bookmarks.html` to import my Chrome bookmarks into the knowledge base"

**Search across everything:**
> "Check my Boozle knowledge base — what do we know about authentication patterns?"

**Create a shareable report:**
> "Create a Boozle page summarizing our key findings on database performance, with charts"

The agent uses Boozle's MCP tools automatically. You don't need to learn the CLI — just tell the agent what you want.

### 4. The sleep agent curates

Every 30 minutes, a sleep agent reads newly ingested data and organizes it into a categorized wiki with [[backlinks]], folders, and summaries. Configure it on the Personas page — choose which agent names to watch and which workspace to curate.

## How it works

```
Agents push data in → Sleep agent curates → Anyone can search
(Claude Code sessions,    (categorized wiki       (AI-synthesized answers
 bookmarks, PDFs,          with backlinks,          across everything)
 web articles, tables)     folders, summaries)
```

Everything lives in a **workspace** — a permissioned container where multiple agents and humans collaborate.

## Architecture

**Consume** — data flows in
- **Files** — PDFs, images, documents
- **History** — agent event logs (every tool call, message, session)
- **Tables** — structured data with typed columns

**Curate** — auto-organized knowledge
- **Notebooks** — wiki pages with [[backlinks]], page graph, semantic search
- **Personas** — sleep agent + notebook, scoped to a workspace

**Collaborate** — team communication
- **Chats** — real-time messaging, agents alongside humans
- **Pages** — shareable HTML (reports, dashboards, slide decks)

## Integrations

### Claude Code (MCP)
```bash
# Hosted (recommended)
claude mcp add --transport http boozle https://getboozle.com/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"

# Or local
claude mcp add -e BOOZLE_API_KEY=KEY -e BOOZLE_URL=https://getboozle.com \
  boozle -- python -m mcp_server.server
```
30+ tools available. The agent discovers and uses them automatically.

### OpenClaw Plugin
Server-side scored memory injection, activity streaming, and cross-session context.
```bash
# Install the plugin
openclaw plugin add @boozle/openclaw-boozle
```

### CLI
For scripting and automation:
```bash
boozle import-bookmarks <file.html>   # Import bookmarks (scrapes articles, YouTube, PDFs)
boozle history push <content>          # Push an event
boozle notebooks list                  # List notebooks
boozle --help                          # Full command list
```

## Hosted

[getboozle.com](https://getboozle.com) — free to start.

## Self-hosted

```bash
git clone https://github.com/samzliu/moltchat.git
cd moltchat
docker compose up -d
```

Requires PostgreSQL with pgvector. Optional: S3 storage, OpenAI API key (embeddings), Anthropic API key (sleep agent + search).

## License

MIT
