
<p align="center">
  <a href="https://joinstash.ai"><img src="docs/assets/logo.svg" alt="Stash" width="320" /></a>
</p>

<h3 align="center">Your team's AI work, compounding.</h3>

<p align="center">
  Most teams run AI individually. Every session starts from zero, and the learnings<br/>
  never aggregate. Stash captures every coding-agent run across your team and turns<br/>
  it into a shared, evolving asset every agent can build on.
</p>


<p align="center">
  <a href="https://github.com/Fergana-Labs/stash/actions/workflows/test.yml"><img src="https://github.com/Fergana-Labs/stash/actions/workflows/test.yml/badge.svg?branch=main" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" /></a>
  <a href="https://joinstash.ai"><img src="https://img.shields.io/badge/Website-joinstash.ai-F97316" alt="Website" /></a>
  <a href="#self-hosted"><img src="https://img.shields.io/badge/Self--hostable-✓-22C55E" alt="Self-hostable" /></a>
  <a href="#privacy"><img src="https://img.shields.io/badge/Transcripts-opt--in-3B82F6" alt="Opt-in transcripts" /></a>
</p>
<p align="center">
  When every agent run feeds the same shared asset, your team stops paying for the same investigation twice.<br/>
  <a href="https://henrydowling.com/agent-velocity.html"><b>Up to 46% of coding work</b></a> today goes to re-investigating fixes earlier sessions already tried and ruled out.<br/>
  Stash recovers it.<br/>
</p>


<!-- GIF #1 — Visualizations of the workspace knowledge base -->
<p align="center">
  <img src="docs/assets/visualizations.gif" alt="Stash visualizations — embedding space, page graph, agent activity" width="900" />
</p>
<!-- GIF #2 — The product in action: agent runs `stash history search`, gets a cited answer -->

<p align="center">
  <img src="docs/assets/product.gif" alt="Stash in action — agent queries shared memory and gets cited answers" width="900" />
</p>

## Table of Contents

- [Why shared beats individual](#why-shared-beats-individual)
- [How it works](#how-it-works)
- [Quick Start](#quick-start)
- [Features](#features)
- [What you get](#what-you-get)
- [Integrations](#integrations)
- [Coming from...](#coming-from)
- [CLI](#cli)
- [Self-Hosted](#self-hosted)
- [Privacy](#privacy)
- [Documentation](#documentation)
- [FAQ](#faq)
- [Latest updates](#latest-updates)
- [Contributing](#contributing)
- [License](#license)

## Why shared beats individual

When five engineers run Claude on the same repo, five different versions of "what we learned" live in five different terminals. Nothing compounds. The sixth question re-debugs the same flaky test someone already solved on Tuesday. Stash is the missing layer: every run becomes part of a shared, evolving asset the whole team, and every agent, can query.

With Stash, every agent on the repo can ask (and answer):

- *"Why did Sam bump the rate limit from 100 to 500?"*
- *"Has anyone already tried fixing the memory leak in auth?"*
- *"What pattern did we land on for background workers last sprint?"*

> "raw data from a given number of sources is collected, then compiled by an LLM into a .md wiki, then operated on by various CLIs by the LLM to do Q&A and to incrementally enhance the wiki… **I think there is room here for an incredible new product instead of a hacky collection of scripts.**"
>
> — Andrej Karpathy, *LLM Knowledge Bases*

**Stash is that product. For teams of coding agents working on the same repo.** Your agents' streamed sessions are the raw data. The wiki is curated automatically by our sleep agent. Everything lands in one workspace your whole team can query. AI usage becomes a shared, evolving asset, not individual effort.

## How it works

**Stream → Curate → Search.** Three steps running over a shared workspace:

1. **Stream** — Prompts, tool calls, and session summaries automatically push to the workspace's history as they happen. Nothing to remember to save.
2. **Curate** — On `SessionEnd`, a curation agent reads recent history and organizes it into wiki notebooks with `[[backlinks]]` and a page graph. Sleep-time compute, not session time. Auto-runs with a 24h cooldown; trigger manually with the `/curate` slash command.
3. **Search** — `stash history search` does full-text search across workspace events. Notebooks and tables support pgvector semantic search via the API. Your agent queries these through the CLI and REST endpoints.

## Quick Start

One line installs the CLI, signs you in, picks a workspace, and installs plugins for your coding agent (auto-detects Claude Code, Cursor, Codex, and OpenCode):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"
```

<p align="center">
  <img src="docs/assets/welcome.png" alt="Stash welcome screen after install" width="900" />
</p>

Then try it:

```bash
stash history search "authentication patterns"      # Full-text search over events
stash history push "session notes here"             # Push an event
stash --help                                        # Full command list
```

<details>
<summary>Manual install</summary>

```bash
pipx install stashai        # or: uv tool install stashai
stash connect               # Interactive: sign in, pick a workspace, install plugin
```

</details>

## Features

| Capability | What it does |
|---|---|
| Shared history | Every prompt, tool call, and session summary streams to a workspace-wide event log. Searchable, filterable, attributable per agent and per human. |
| Sleep-time curation | On `SessionEnd`, a curation agent reads recent history and writes wiki notebooks with `[[backlinks]]` and a page graph. 24-hour cooldown; manual via `/curate`. |
| Search | `stash history search` for full-text search over events. Notebooks and tables support pgvector semantic search via the REST API. |
| Wiki notebooks | Rich collaborative pages with wiki-style links, page-graph visualization, backlinks, and pgvector semantic search. |
| Visualizations | See the team's memory as it forms — embedding projections, page graphs, knowledge-density treemaps, agent-activity heatmaps. |
| Local-first option | Self-host the entire stack with Docker Compose. Embeddings default to local sentence-transformers — zero API keys required to run. |
| Real-time rooms | Agents and humans chat side-by-side in workspace channels. Coordinate, hand off, unblock — all in one place. *Coming soon* |
| Shareable pages | Publish reports, dashboards, and HTML deliverables behind a link. No login walls between teams. *Coming soon* |

## What you get

Stash organizes your team's agent activity into a workspace that looks like this:

```text
your-workspace/
├── history/                       # append-only event log — every prompt, tool call, summary
│   └── (streamed live from every agent + human)
├── notebooks/                     # auto-curated wiki, written by stash:sleep
│   ├── auth-patterns.md           #   ...with [[backlinks]] between pages
│   ├── memory-leak-v2.md          #   ...folder structure inferred from your work
│   └── rate-limits/
│       ├── gateway-500-per-min.md
│       └── batch-import-flow.md
├── tables/                        # structured data with optional row embeddings
└── files/                         # PDFs, screenshots, attachments (S3-compatible)
```

A live page graph, embedding projection, and knowledge-density treemap render over the same workspace — the visualizations you see in the GIFs above.

## Integrations

The one-line installer auto-detects which agent you have and wires up the plugin. To install one manually:

| Agent | Plugin | Install |
|-------|--------|---------|
| **Claude Code** | [`plugins/claude-plugin`](plugins/claude-plugin/README.md) | `claude plugin marketplace add Fergana-Labs/stash && claude plugin install stash@stash-plugins` |
| **Cursor** | [`plugins/cursor-plugin`](plugins/cursor-plugin/README.md) | symlinks `hooks.json` into `~/.cursor/` — see plugin README |
| **Codex** | [`plugins/codex-plugin`](plugins/codex-plugin/README.md) | renders `hooks.json` into `~/.codex/` — see plugin README |
| **OpenCode** | [`plugins/opencode-plugin`](plugins/opencode-plugin/README.md) | adds a `plugin` entry to `~/.config/opencode/opencode.json` |
| **Gemini CLI** | [`plugins/gemini-plugin`](plugins/gemini-plugin/README.md) | merges hooks into `~/.gemini/settings.json` |
| **Openclaw** | [`plugins/openclaw-plugin`](plugins/openclaw-plugin/README.md) | `openclaw plugins install github:Fergana-Labs/stash#plugins/openclaw-plugin` |

Every plugin streams session activity to the same workspace and gives the agent access to the shared `stash` CLI. Mix and match — different teammates can use different agents against the same shared brain.

## Coming from...

Stash sits alongside whatever you have today. Here's how it maps:

| You're using | What Stash gives you on top |
|--------------|-----------------------------|
| `CLAUDE.md` / `AGENTS.md`/ Built-in agent memory | A shared, searchable, multi-agent version that updates itself from real session data. Single source for agent session history about your code. |
| Mem0 / Letta / Supermemory | MIT-licensed, self-hostable, with team collaboration and UI |
| Notion / Confluence | Session history automatically pushed. Pages curated automatically by your agent. No one has to remember to write the doc. |
| Slack threads | A persistent, searchable record that survives the 90-day retention cliff and is queryable by your agents. |

## CLI

```bash
stash connect                        # Sign in, pick a workspace, install plugin
stash history search <query>         # Full-text search over history events
stash history push <content>         # Push an event
stash notebooks list --all           # List notebooks across your workspaces
stash tables list                    # List tables in the workspace
stash files list                     # List uploaded files
stash settings                      # Interactive settings page
stash --help                         # Full command list
```

Every command accepts `--json` for machine-readable output and `--ws ID` to target a specific workspace. Full reference at [joinstash.ai/docs/cli](https://joinstash.ai/docs/cli).

## Self-Hosted

```bash
git clone https://github.com/Fergana-Labs/stash.git
cd stash
cp .env.example .env          # fill in credentials + API keys
# edit Caddyfile → replace app.example.com with your domain
docker compose -f docker-compose.prod.yml up -d
```

Brings up four containers: PostgreSQL 16 + pgvector, FastAPI backend (`:3456`), Next.js frontend (`:3457`), and Caddy for automatic HTTPS via Let's Encrypt. Alembic migrations run on backend startup.

Embeddings default to local sentence-transformers — no API keys required to run. Set `EMBEDDING_PROVIDER` to switch to OpenAI, Hugging Face, or any OpenAI-compatible endpoint. Optional S3-compatible object storage (R2, S3, MinIO) for file uploads.

> Local development? Use `docker compose up -d` (no `-f` flag) — simple setup with hardcoded dev credentials.

## Privacy

Stash is built so you can keep your team's memory under your control:

- **Transcripts are opt-in.** You can give your agent shared *read* access to the workspace's memory without uploading any of your own session data.
- **No LLM calls from the server.** Curation and search run inside your agent (Claude Code, Cursor, etc.) using the keys it already has. The Stash backend itself makes no model calls.
- **Self-hostable end-to-end.** One Docker Compose file. PostgreSQL + pgvector, local sentence-transformer embeddings, no required external API keys.
- **Permissioned workspaces.** On the hosted version, only invited members can read or write a workspace. Public visibility is per-resource, opt-in.

## Documentation

| Document | What it covers |
|----------|---------------|
| [Quickstart](https://joinstash.ai/docs/quickstart) | Install the CLI, connect your agent, push your first events |
| [Concepts](https://joinstash.ai/docs/concepts) | Workspaces, history, notebooks, tables, files, search, curation |
| [CLI](https://joinstash.ai/docs/cli) | Every command, every flag |
| [Self-hosting](https://joinstash.ai/docs/self-hosting) | Full Docker Compose deploy with environment reference |
| [Architecture](ARCHITECTURE.md) | System diagram, data model, backend/frontend structure |
| [Use Cases](USE_CASES.md) | End-to-end scenarios — team KB, research, multi-agent |
| [Contributing](CONTRIBUTING.md) | Local dev setup, running tests, submitting PRs |
| [Design System](DESIGN.md) | Colors, typography, spacing, agent/human visual language |
| [Testing](TESTING.md) | Test frameworks, suites, conventions |
| [Security](SECURITY.md) | Vulnerability reporting policy |
| [Changelog](CHANGELOG.md) | Release history |

## FAQ

**What LLMs does Stash use?**
None on the server. Curation runs inside your agent (Claude Code, Cursor, etc.) as a plugin skill, so it uses whatever model and keys the agent is already configured with — the Stash backend itself makes no LLM calls. Embeddings are pluggable and default to local sentence-transformers (no key). Set `EMBEDDING_PROVIDER` in `.env` to switch to OpenAI, Hugging Face, or any OpenAI-compatible endpoint.

**Can I use this without Claude Code?**
Yes. The CLI and REST API work standalone with any client, and there are first-party plugins for Cursor, Codex, OpenCode, Gemini CLI, and Openclaw.

**Where does the "save up to 46%" number come from?**
A 4-session memory-leak benchmark documented in [*On Agent Velocity*](https://henrydowling.com/agent-velocity.html) by Henry Dowling (one of Stash's maintainers). Without transcript sharing, nearly half of agent actions re-investigated fixes earlier sessions had already tried and ruled out. With shared transcripts, wasted work dropped ~97% and tool calls dropped ~50%.

## Latest updates

- **2026-04-22** — Initial open-source release

For the full log, see [`CHANGELOG.md`](CHANGELOG.md).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Found a bug? [Open an issue](https://github.com/Fergana-Labs/stash/issues).

## Maintainers

| Name | Role | Contact |
|------|------|---------|
| [@henry-dowling](https://github.com/henry-dowling) | Creator & Lead maintainer | GitHub issues or [support@ferganalabs.com](mailto:support@ferganalabs.com) for vulnerabilities |
| [@samzliu](https://github.com/samzliu) | Creator | GitHub issues |
| [@triobaba](https://github.com/triobaba) | Creator | GitHub issues |

## License

[MIT](LICENSE) — Copyright (c) 2026 Fergana Labs

---

<p align="center">
  Built by <a href="https://ferganalabs.com">Fergana Labs</a>.
</p>
