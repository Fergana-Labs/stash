
<p align="center">
  <a href="https://joinstash.ai"><img src="docs/assets/logo.svg" alt="Stash" width="320" /></a>
</p>

<h3 align="center">Knowledge bases for the agent era.</h3>

<p align="center">
  The one place your agents connect to all your data — GitHub, Drive, Gmail, <br>
  Notion, Slack and more — plus an agent-native Drive in Markdown and HTML <br>
  where their sessions, files, and pages all land.
</p>


<p align="center">
  <a href="https://github.com/Fergana-Labs/stash/actions/workflows/test.yml"><img src="https://github.com/Fergana-Labs/stash/actions/workflows/test.yml/badge.svg?branch=main" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" /></a>
  <a href="https://joinstash.ai"><img src="https://img.shields.io/badge/Website-joinstash.ai-F97316" alt="Website" /></a>
  <a href="#self-hosted"><img src="https://img.shields.io/badge/Self--hostable-✓-22C55E" alt="Self-hostable" /></a>
  <a href="#privacy"><img src="https://img.shields.io/badge/Transcripts-opt--in-3B82F6" alt="Opt-in transcripts" /></a>
  <a href="https://discord.gg/PVFdcQx2u3"><img src="https://img.shields.io/badge/Discord-Join%20us-5865F2?logo=discord&logoColor=white" alt="Discord" /></a>
</p>
<p align="center">
  When we tested this internally, we found that it sped up long-running instances of Claude Code by <a href="https://henrydowling.com/agent-velocity.html"><b>49%</b></a>.<br/>
</p>


<!-- Screenshot #1 — The Memory page: wiki graph, knowledge map, recent edits -->
<p align="center">
  <img src="docs/assets/memory.png" alt="Stash Memory — wiki knowledge graph, file system, and recent agent activity" width="900" />
</p>
<!-- GIF #2 — The product in action: agent runs `stash search`, gets a cited answer -->

<p align="center">
  <img src="docs/assets/product.gif" alt="Stash in action — agent queries shared memory and gets cited answers" width="900" />
</p>

## How it works

- **Sessions stream in automatically.** A hook for your coding agent pushes every transcript — prompts, tool calls, artifacts — into your Stash.
- **Files and sessions live side by side.** Markdown, HTML, tables, PDFs. You and your agents both write here; both sides see edits in real time.
- **Agents query it like a filesystem.** A CLI, MCP server, and virtual-filesystem shell expose your Stash to any agent. Semantic and keyword search across pages, sessions, and tables.
- **Skills are the shareable slice.** Bundle pages and sessions into one link. Publish to the world, fork a public Skill into your own Stash, or `stash skills install` one into your agent — installed skills auto-update at session start, and `stash skills follow` auto-installs skills people share with you.
- **Bring your own MCP servers.** Register MCP servers once (Tools page or `stash tools add`); your cloud agent gets them automatically and `stash tools install` writes them into any local agent's `.mcp.json`.

## Why persistent beats per-session

When you run Claude on a repo, you generate valuable session transcripts. However, your coding agent can only access transcripts generated on the machine where the agent is currently running. As a result, work is duplicated and velocity is decreased. This is especially true as coding agents begin to run autonomously for significant periods of time.

With Stash, every agent run has context about every session you've created. Here are some use cases:

- **Code Faster / Don't Duplicate Work**: "Have I tried fixing the memory leak in our API gateway before? What was attempted?"
- **Stay Organized**: "What did I get done this week? What other work did I do that isn't tracked in Git?"
- **Recover Lost Context**: "Why did I increase the timeout to 30s? The git history is unhelpful."
- **Pick Up Where You Left Off**: "Please add a feedback endpoint to our API" -> Claude: "FYI, you decided earlier not to add a feedback endpoint since we want to encourage churned users to hop on a call directly"

> "raw data from a given number of sources is collected, then compiled by an LLM into a .md knowledge base, then operated on by various CLIs by the LLM to do Q&A and to incrementally enhance it… **I think there is room here for an incredible new product instead of a hacky collection of scripts.**"
>
> — Andrej Karpathy, *LLM Knowledge Bases*

**Stash is that product.** The one place your agents connect to all your data, with an agent-native Drive they write it back into — not a stack of shell scripts wrapped around a folder of markdown.

Built for —

| Use case | What teams put in it |
|---|---|
| **Engineering live docs** | coding-agent plans, ADRs, and design notes that stay current |
| **Second brain** | the persistent context every one of your agents reads from |
| **Research knowledge base** | long-running PKBs with sources, transcripts, and tables |
| **Ops playbooks** | release runbooks and on-call procedures |
| **Brand voice** | editorial guidelines and copy standards agents write to |
| **Personal knowledge management** | notes, drafts, and scratch files for a single operator |

## Quick Start

```bash
uv tool install stashai
stash signin
```

`stash signin` walks you through sign-in, connects your current repo when
you want uploads, and wires up coding-agent plugins. Use `stash connect`
later when you are already authenticated and only need to bind another repo.

<details>
<summary>Prefer a one-liner?</summary>

```bash
bash -c "$(curl -fsSL https://joinstash.ai/install)"
```

The installer uses `uv` to install or update `stashai`, bootstrapping `uv`
when needed, and then runs `stash signin`.
Use this when you don't already have a Python toolchain on your machine.

</details>

<p align="center">
  <img src="docs/assets/welcome.png" alt="Stash welcome screen after install" width="900" />
</p>

Then try it: ask your coding agent if it has access to Stash.

<p align="center">
  <img src="docs/assets/agent-access.png" alt="Coding agent confirming access to the Stash CLI" width="900" />
</p>

Agents can browse Stash with an app-level virtual filesystem shell:

```bash
stash vfs ls /
stash vfs "tree / -L 2"
stash vfs "find / -maxdepth 3 -type f | head -n 20"
stash vfs "rg \"database migration\" /"
```

## Integrations

Stash supports the following coding agents:
- **Claude Code** 
- **Cursor** 
- **Codex** 
- **OpenCode**
- **Gemini CLI**
- **Openclaw** 
- **Hermes**

Stash supports opt in per-coding agent. `stash signin` detects every agent on your machine and auto-installs its hooks — pick which ones during signin. Mix and match — different teammates can use different agents against the same shared brain. (Openclaw's code scanner requires its unsafe-install flag, which the installer passes; Hermes asks you to approve the hooks once via `hermes hooks list`.)

## CLI Reference

See [here](https://www.joinstash.ai/docs/cli) for a CLI reference.

## Self-Hosted

Run Stash with prebuilt GHCR images:

To host locally:

```bash
git clone https://github.com/Fergana-Labs/stash.git
cd stash
cp .env.example .env
docker compose -f docker-compose.prod.yml -f docker-compose.local.yml pull
docker compose -f docker-compose.prod.yml -f docker-compose.local.yml up -d
curl http://localhost:3456/health
open http://localhost:3457/login
```

Docker Compose generates and persists the OAuth token encryption key when
`INTEGRATIONS_ENCRYPTION_KEY` is unset. Set it yourself only if you manage
deployment secrets outside Compose.

For a public domain with Caddy and HTTPS:

```bash
# Set PUBLIC_URL and CORS_ORIGINS in .env, then replace app.example.com in Caddyfile.
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
curl https://app.example.com/health
```

`docker-compose.prod.yml` pins the image versions it was tested with. To
upgrade, pull the latest compose file and restart:

```bash
git pull
docker compose -f docker-compose.prod.yml -f docker-compose.local.yml pull
docker compose -f docker-compose.prod.yml -f docker-compose.local.yml up -d
```

Then install the CLI:

```bash
uv tool install stashai
cd /path/to/the/repo/you/want/to/connect
stash signin   # choose "Self-host" and enter http://localhost:3456
```

When connecting to a domain-backed install, enter your public URL (e.g.
`https://app.example.com`) at the same prompt. To change the endpoint later,
run `stash settings`.

Finally see it in action:

```
claude
> what did I get done last week? check stash.
```

## Privacy

Stash is built for engineering teams working in private repos.

- **LLM calls are optional and scoped.** When an Anthropic API key is configured, the server uses it for ask-the-stash answers and auto-generated session titles. No key means those features are unavailable — the rest of Stash works without any LLM.
- **Private by default.** Your Stash is yours alone. Public visibility is controlled by Skills.
- **Transcripts are opt-in.** If you don't want to upload your agent transcripts, you can give your agent *read* access to your Stash without uploading any of your own session data.
  
## FAQ

**What LLMs does Stash use?**
When an Anthropic API key is provided, the server calls Claude for ask-the-stash (quality tier) and session title generation. Both are optional — without the key, Stash works but those features are disabled. There is one background writer: the Memory curator, a scheduled agent that maintains your Memory wiki from new sessions and files; it only writes inside the reserved Memory folder.

**Can I use this without Claude Code?**
Yes. You can use the CLI with anything, and Stash has native plugins for Cursor, Codex, Opencode, Gemini CLI, and more.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Found a bug? [Open an issue](https://github.com/Fergana-Labs/stash/issues).

## License

[MIT](LICENSE) — Copyright (c) 2026 Fergana Labs

---

<p align="center">
  Built by <a href="https://ferganalabs.com">Fergana Labs</a>.
</p>
