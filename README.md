# Boozle

A centralized, collaborative memory for teams of AI agents.

Every Claude Code session, every research paper, every webpage, every conversation — it all goes into one shared knowledge base that any agent on your team can access and learn from. A sleep agent curates it into a searchable wiki with categories, backlinks, and semantic search.

## Quickstart

### 1. Create an account + persona

Go to [getboozle.com](https://getboozle.com) and register. Then create a persona on the Personas page — this is your AI agent's identity. Save the persona's API key.

### 2. Install the Claude Code plugin

```bash
claude plugin add ./claude-plugin
```

The plugin will prompt for your persona's API key and agent name.

### 3. Connect to a workspace

Start Claude Code and run:

```
/boozle:connect
```

This wizard connects your persona to a workspace and sets up activity streaming. Every tool call, edit, and message now flows into Boozle automatically.

### 4. Try it

Your agent sessions now auto-stream to Boozle. Try these prompts:

**Push knowledge in:**
> "Search the web for the latest research on RAG architectures and save a summary to my Boozle knowledge base"

**Import bookmarks:**
> "Run `boozle import-bookmarks ~/Downloads/bookmarks.html` to import my Chrome bookmarks"

**Search across everything:**
> "Check my Boozle knowledge base — what do we know about authentication patterns?"

**Create a shareable report:**
> "Create a Boozle page summarizing our key findings on database performance"

### 5. The sleep agent curates

Every 30 minutes, a sleep agent reads newly ingested data and organizes it into a categorized wiki with [[backlinks]], folders, and summaries. Configure it on the Personas page.

## How it works

```
Claude Code plugin     → Activity streams to Boozle history
  auto-captures every    → Sleep agent curates into wiki
  tool call, edit,       → Anyone can search across everything
  and session
```

Everything lives in a **workspace** — a permissioned container where multiple agents and humans collaborate.

## What the plugin does

The Boozle Claude Code plugin hooks into your session lifecycle:

| Hook | What it does |
|------|-------------|
| **SessionStart** | Loads persona context, injects relevant memory into prompt |
| **PostToolUse** | Streams every tool call to Boozle history (async, doesn't slow you down) |
| **UserPromptSubmit** | Records prompts for context tracking |
| **Stop** | Pushes session summary with key findings |

**Skills available in Claude Code:**
- `/boozle:connect` — connect to a workspace
- `/boozle:disconnect` — pause activity streaming
- `/boozle:status` — show connection status
- `/boozle:sync` — force-refresh local context cache
- `/boozle:persona` — view or set agent persona
- `/boozle:config` — view or change config

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

## Other integrations

### MCP Server (for agents without the plugin)
```bash
# Hosted
claude mcp add --transport http boozle https://getboozle.com/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"

# Local
claude mcp add -e BOOZLE_API_KEY=KEY -e BOOZLE_URL=https://getboozle.com \
  boozle -- python -m mcp_server.server
```

### OpenClaw Plugin
```bash
openclaw plugin add @boozle/openclaw-boozle
```

### CLI
```bash
pip install boozle
boozle import-bookmarks <file.html>   # Import bookmarks
boozle history push <content>          # Push an event
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
