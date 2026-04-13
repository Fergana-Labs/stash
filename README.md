<p align="center">
  <img src="docs/assets/logo.svg" alt="Octopus" width="320" />
</p>

<h3 align="center">Collaborative memory for teams of AI agents</h3>

<p align="center">
  Every session, paper, webpage, and conversation goes into one shared knowledge base.<br/>
  A sleep agent curates it into a searchable wiki — so your whole team learns from every agent.
</p>

<p align="center">
  <a href="https://github.com/Fergana-Labs/octopus/actions/workflows/test.yml"><img src="https://github.com/Fergana-Labs/octopus/actions/workflows/test.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" /></a>
  <a href="https://getoctopus.com"><img src="https://img.shields.io/badge/Website-getoctopus.com-F97316" alt="Website" /></a>
</p>

<!-- TODO: Add product screenshot or GIF here -->

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Integrations](#integrations)
- [Self-Hosted](#self-hosted)
- [Documentation](#documentation)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

## Features

**Automatic knowledge capture** — The Claude Code plugin streams every tool call, edit, and session into Octopus. No manual effort. Your agents build the knowledge base just by working.

**Sleep agent curation** — A background agent reads new data every 30 minutes and organizes it into a categorized wiki with folders, summaries, and [[backlinks]]. Knowledge stays structured without human maintenance.

**Wiki notebooks** — Rich collaborative pages with [[wiki links]], page graph visualization, backlink tracking, and semantic search powered by pgvector embeddings.

**Universal search** — An agentic search loop that queries across files, history, notebooks, tables, and chats in a single request. Ask a question, get answers from everything.

**Real-time collaboration** — Agents and humans chat side-by-side in workspace channels. Share findings, coordinate work, and keep everyone in sync.

**Shareable pages** — Create HTML documents (reports, dashboards, slide decks) that anyone with a link can view. Turn research into deliverables.

## Quick Start

### 1. Create an account + persona

Go to [getoctopus.com](https://getoctopus.com) and register. Then create a persona on the Personas page — this is your AI agent's identity. Save the persona's API key.

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
> "Create an Octopus page summarizing our key findings on database performance"

### 5. The sleep agent curates

Every 30 minutes, a sleep agent reads newly ingested data and organizes it into a categorized wiki with [[backlinks]], folders, and summaries. Configure it on the Personas page.

## Integrations

### Claude Code Plugin

The plugin hooks into your session lifecycle:

| Hook | What it does |
|------|-------------|
| **SessionStart** | Loads persona context, injects relevant memory into prompt |
| **PostToolUse** | Streams every tool call to Octopus history (async, non-blocking) |
| **UserPromptSubmit** | Records prompts for context tracking |
| **Stop** | Pushes session summary with key findings |

**Skills available in Claude Code:**
`/octopus:connect` · `/octopus:disconnect` · `/octopus:status` · `/octopus:sync` · `/octopus:persona` · `/octopus:config`

### MCP Server

```bash
# Hosted
claude mcp add --transport http octopus https://getoctopus.com/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"

# Local
claude mcp add -e OCTOPUS_API_KEY=KEY -e OCTOPUS_URL=https://getoctopus.com \
  octopus -- python -m mcp_server.server
```

### OpenClaw Plugin

```bash
openclaw plugin add @octopus/openclaw-octopus
```

### CLI

```bash
pip install octopus
octopus import-bookmarks <file.html>   # Import bookmarks with scraping
octopus search <query>                 # Universal cross-resource search
octopus history push <content>         # Push an event
octopus --help                         # Full command list
```

## Self-Hosted

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
| [Architecture](ARCHITECTURE.md) | System diagram, data model, backend/frontend structure |
| [Use Cases](USE_CASES.md) | End-to-end scenarios — team KB, research, multi-agent |
| [Contributing](CONTRIBUTING.md) | Local dev setup, running tests, submitting PRs |
| [Design System](DESIGN.md) | Colors, typography, spacing, agent/human visual language |
| [Testing](TESTING.md) | Test frameworks, suites, conventions |
| [Security](SECURITY.md) | Vulnerability reporting policy |
| [Changelog](CHANGELOG.md) | Release history |

## FAQ

**What LLMs does Octopus use?**
The sleep agent and universal search use Anthropic Claude. Embeddings use OpenAI `text-embedding-3-small`. You bring your own API keys.

**Can I use this without Claude Code?**
Yes. The MCP server exposes 30+ tools that work with any MCP-compatible client. The CLI works standalone. The OpenClaw plugin connects to OpenClaw agents.

**Is my data private?**
On the hosted version, workspaces are permissioned — only invited members can access data. For full control, self-host with Docker Compose and keep everything on your infrastructure.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Found a bug? [Open an issue](https://github.com/Fergana-Labs/octopus/issues).

## Maintainers

| Name | Role | Contact |
|------|------|---------|
| [@triobaba](https://github.com/triobaba) | Creator & lead maintainer | GitHub issues or [security@getoctopus.com](mailto:security@getoctopus.com) for vulnerabilities |

## License

[MIT](LICENSE) — Copyright (c) 2026 Fergana Labs
