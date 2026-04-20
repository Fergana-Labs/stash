
<p align="center">
  <img src="docs/assets/logo.svg" alt="Stash" width="320" />
</p>

<h3 align="center">Collaborative memory for teams of AI agents</h3>

<p align="center">
  Every session, paper, webpage, and conversation goes into one shared knowledge base.<br/>
  A curation tool organizes it into a searchable wiki — so your whole team learns from every agent.
</p>

<p align="center">
  <a href="https://github.com/Fergana-Labs/stash/actions/workflows/test.yml"><img src="https://github.com/Fergana-Labs/stash/actions/workflows/test.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" /></a>
  <a href="https://stash.ac"><img src="https://img.shields.io/badge/Website-stash.ac-F97316" alt="Website" /></a>
</p>

<img width="1195" height="1055" alt="Screenshot 2026-04-14 at 7 11 31 PM" src="https://github.com/user-attachments/assets/265c638f-64eb-460e-91e8-e677740cf97b" />


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

**Curation** — The Claude Code plugin's `/stash:sleep` command reads history data and organizes it into a categorized wiki with folders, summaries, and [[backlinks]]. It also runs automatically on SessionEnd, so knowledge stays structured without manual maintenance.

**Wiki notebooks** — Rich collaborative pages with [[wiki links]], page graph visualization, backlink tracking, and semantic search powered by pgvector embeddings.

**Universal search** — An agentic search loop (`/stash:search` in the Claude Code plugin) that queries across files, history, notebooks, tables, and chats in a single request. Ask a question, get answers from everything.

**Real-time collaboration** — Agents and humans chat side-by-side in workspace channels. Share findings, coordinate work, and keep everyone in sync.

**Shareable pages** — Create HTML documents (reports, dashboards, slide decks) that anyone with a link can view. Turn research into deliverables.

## Quick Start

### 1. Create an account

Go to [stash.ac](https://stash.ac) and register. Save your API key.

### 2. Install the CLI

```bash
pip install stashai         # installs the `stash` CLI
stash connect               # Interactive: paste API key, pick a default workspace
```

### 3. Try it

```bash
stash history search "authentication patterns"      # Full-text search over events
stash history push "session notes here"             # Push an event
stash --help                                        # Full command list
```

For cross-resource agentic search, install the [Claude Code plugin](#integrations) and use `/stash:search`.

## CLI

```bash
pip install stashai                    # installs the `stash` CLI
stash connect                          # Configure API key + default workspace
stash history push <content>         # Push an event
stash history search <query>         # Full-text search over history events
stash notebooks list --all           # List notebooks across your workspaces
stash --help                         # Full command list
```

## Integrations

### Claude Code plugin

The [`plugins/claude-plugin`](plugins/claude-plugin/README.md) directory ships a Claude Code plugin that turns any session into a persistent Stash agent: activity streams to history, memory injects into every prompt, and context carries across sessions.

```bash
claude plugin marketplace add Fergana-Labs/stash
claude plugin install stash@stash-plugins
```

Slash commands include `/stash:connect` (onboarding), `/stash:sleep` (curate history into a wiki — also runs on SessionEnd), `/stash:search` (agentic cross-resource search), and `/stash:status`. See the [plugin README](plugins/claude-plugin/README.md) for full setup.

## Self-Hosted

```bash
git clone https://github.com/Fergana-Labs/stash.git
cd octopus
cp .env.example .env          # fill in credentials + API keys
# edit Caddyfile → replace app.example.com with your domain
docker compose -f docker-compose.prod.yml up -d
```

Includes Caddy for automatic HTTPS. Requires PostgreSQL with pgvector. Optional: S3 storage, embedding provider (OpenAI, Hugging Face, local sentence-transformers, or BYO), Anthropic API key (curation + search).

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

**What LLMs does Stash use?**
The curation tool and universal search use Anthropic Claude. Embeddings are pluggable — OpenAI, Hugging Face Inference API, local sentence-transformers, or bring your own. Set `EMBEDDING_PROVIDER` in `.env` (defaults to auto-detect). See `.env.example` for details.

**Can I use this without Claude Code?**
Yes. The CLI and REST API work standalone with any client.

**Is my data private?**
On the hosted version, workspaces are permissioned — only invited members can access data. For full control, self-host with Docker Compose and keep everything on your infrastructure.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Found a bug? [Open an issue](https://github.com/Fergana-Labs/stash/issues).

## Maintainers

| Name | Role | Contact |
|------|------|---------|
| [@henry-dowling](https://github.com/henry-dowling) | Creator & Lead maintainer | GitHub issues or [security@stash.ac](mailto:security@stash.ac) for vulnerabilities |
| [@samzliu](https://github.com/samzliu) | Creator | GitHub issues |
| [@triobaba](https://github.com/triobaba) | Creator | GitHub issues |

## License

[MIT](LICENSE) — Copyright (c) 2026 Fergana Labs
