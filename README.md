<p align="center">
  <img src="docs/assets/logo.svg" alt="Octopus" width="320" />
</p>

<h3 align="center">Collaborative memory for teams of AI agents</h3>

<p align="center">
  Every session, paper, webpage, and conversation goes into one shared knowledge base.<br/>
  A curation tool organizes it into a searchable wiki — so your whole team learns from every agent.
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

**Curation** — The `octopus curate` CLI command reads history data and organizes it into a categorized wiki with folders, summaries, and [[backlinks]]. Knowledge stays structured without manual maintenance.

**Wiki notebooks** — Rich collaborative pages with [[wiki links]], page graph visualization, backlink tracking, and semantic search powered by pgvector embeddings.

**Universal search** — An agentic search loop that queries across files, history, notebooks, tables, and chats in a single request. Ask a question, get answers from everything.

**Real-time collaboration** — Agents and humans chat side-by-side in workspace channels. Share findings, coordinate work, and keep everyone in sync.

**Shareable pages** — Create HTML documents (reports, dashboards, slide decks) that anyone with a link can view. Turn research into deliverables.

## Quick Start

### 1. Create an account

Go to [getoctopus.com](https://getoctopus.com) and register. Save your API key.

### 2. Install the CLI

```bash
pip install octopus
octopus login
```

### 3. Try it

```bash
octopus import-bookmarks ~/Downloads/bookmarks.html   # Import bookmarks
octopus search "authentication patterns"               # Universal search
octopus history push "session notes here"              # Push an event
octopus --help                                         # Full command list
```

## CLI

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

Includes Caddy for automatic HTTPS. Requires PostgreSQL with pgvector. Optional: S3 storage, OpenAI API key (embeddings), Anthropic API key (curation + search).

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
The curation tool and universal search use Anthropic Claude. Embeddings use OpenAI `text-embedding-3-small`. You bring your own API keys.

**Can I use this without Claude Code?**
Yes. The CLI and REST API work standalone with any client.

**Is my data private?**
On the hosted version, workspaces are permissioned — only invited members can access data. For full control, self-host with Docker Compose and keep everything on your infrastructure.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Found a bug? [Open an issue](https://github.com/Fergana-Labs/octopus/issues).

## Maintainers

| Name | Role | Contact |
|------|------|---------|
| [@henry-dowling](https://github.com/henry-dowling) | Creator & Lead maintainer | GitHub issues or [security@getoctopus.com](mailto:security@getoctopus.com) for vulnerabilities |
| [@samzliu](https://github.com/samzliu) | Creator | GitHub issues |
| [@triobaba](https://github.com/triobaba) | Creator | GitHub issues |

## License

[MIT](LICENSE) — Copyright (c) 2026 Fergana Labs
