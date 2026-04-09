# Octopus

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
/octopus:connect
```

This wizard connects your persona to a workspace and sets up activity streaming. Every tool call, edit, and message now flows into Octopus automatically.

### 4. Try it

Your agent sessions now auto-stream to Octopus. Try these prompts:

**Push knowledge in:**
> "Search the web for the latest research on RAG architectures and save a summary to my Octopus knowledge base"

**Import bookmarks:**
> "Run `octopus import-bookmarks ~/Downloads/bookmarks.html` to import my Chrome bookmarks"

**Search across everything:**
> "Check my Octopus knowledge base — what do we know about authentication patterns?"

**Create a shareable report:**
> "Create a Octopus page summarizing our key findings on database performance"

### 5. The sleep agent curates

Every 30 minutes, a sleep agent reads newly ingested data and organizes it into a categorized wiki with [[backlinks]], folders, and summaries. Configure it on the Personas page.

## How it works

```
Claude Code plugin     → Activity streams to Octopus history
  auto-captures every    → Sleep agent curates into wiki
  tool call, edit,       → Anyone can search across everything
  and session
```

Everything lives in a **workspace** — a permissioned container where multiple agents and humans collaborate.

## What the plugin does

The Octopus Claude Code plugin hooks into your session lifecycle:

| Hook | What it does |
|------|-------------|
| **SessionStart** | Loads persona context, injects relevant memory into prompt |
| **PostToolUse** | Streams every tool call to Octopus history (async, doesn't slow you down) |
| **UserPromptSubmit** | Records prompts for context tracking |
| **Stop** | Pushes session summary with key findings |

**Skills available in Claude Code:**
- `/octopus:connect` — connect to a workspace
- `/octopus:disconnect` — pause activity streaming
- `/octopus:status` — show connection status
- `/octopus:sync` — force-refresh local context cache
- `/octopus:persona` — view or set agent persona
- `/octopus:config` — view or change config

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
claude mcp add --transport http octopus https://getboozle.com/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"

# Local
claude mcp add -e OCTOPUS_API_KEY=KEY -e OCTOPUS_URL=https://getboozle.com \
  octopus -- python -m mcp_server.server
```

### OpenClaw Plugin
```bash
openclaw plugin add @octopus/openclaw-octopus
```

### CLI
```bash
pip install octopus
octopus import-bookmarks <file.html>   # Import bookmarks
octopus history push <content>          # Push an event
octopus --help                          # Full command list
```

## Hosted

[getboozle.com](https://getboozle.com) — free to start.

## Self-hosted

```bash
git clone https://github.com/Fergana-Labs/octopus.git
cd octopus
cp .env.example .env          # fill in credentials + API keys
# edit Caddyfile → replace app.example.com with your domain
docker compose -f docker-compose.prod.yml up -d
```

Includes Caddy for automatic HTTPS. Requires PostgreSQL with pgvector. Optional: S3 storage, OpenAI API key (embeddings), Anthropic API key (sleep agent + search).

> Local development? Use `docker compose up -d` (no `-f` flag) — simple setup with hardcoded dev credentials.

## Documentation

| Document | What it covers |
|----------|---------------|
| [Architecture](ARCHITECTURE.md) | System diagram, data model, backend/frontend structure, deployment |
| [Use Cases](USE_CASES.md) | 7 end-to-end scenarios — team KB, research, multi-agent, self-hosted |
| [Contributing](CONTRIBUTING.md) | Local dev setup, running tests, submitting PRs |
| [Design System](DESIGN.md) | Colors, typography, spacing, agent/human visual language |
| [Testing](TESTING.md) | Test frameworks, suites, conventions |
| [Security](SECURITY.md) | Vulnerability reporting policy |
| [Changelog](CHANGELOG.md) | Release history |

In-app docs are available at `/docs` when running the frontend.

## Maintainers

| Name | Role | Contact |
|------|------|---------|
| [@triobaba](https://github.com/triobaba) | Creator & lead maintainer | GitHub issues or [security@getboozle.com](mailto:security@getboozle.com) for vulnerabilities |

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## License

MIT
