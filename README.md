
<p align="center">
  <a href="https://joinstash.ai"><img src="docs/assets/logo.svg" alt="Stash" width="320" /></a>
</p>

<h3 align="center">Knowledge bases for the agent era.</h3>

<p align="center">
  Built for the era where your agents write more than your team does. <br>
  Sessions, files, and Stashes — a company brain humans and agents both <br>
  write into, query semantically, and publish from.
</p>


<p align="center">
  <a href="https://github.com/Fergana-Labs/stash/actions/workflows/test.yml"><img src="https://github.com/Fergana-Labs/stash/actions/workflows/test.yml/badge.svg?branch=main" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" /></a>
  <a href="https://joinstash.ai"><img src="https://img.shields.io/badge/Website-joinstash.ai-F97316" alt="Website" /></a>
  <a href="#self-hosted"><img src="https://img.shields.io/badge/Self--hostable-✓-22C55E" alt="Self-hostable" /></a>
  <a href="#privacy"><img src="https://img.shields.io/badge/Transcripts-opt--in-3B82F6" alt="Opt-in transcripts" /></a>
  <a href="https://discord.gg/CRepGtEx"><img src="https://img.shields.io/badge/Discord-Join%20us-5865F2?logo=discord&logoColor=white" alt="Discord" /></a>
</p>
<p align="center">
  When we tested this internally, we found that it sped up long-running instances of Claude Code by <a href="https://henrydowling.com/agent-velocity.html"><b>49%</b></a>.<br/>
</p>


<!-- GIF #1 — Visualizations of the workspace knowledge base -->
<p align="center">
  <img src="docs/assets/visualizations.gif" alt="Stash visualizations — embedding space, file tree, agent activity" width="900" />
</p>
<!-- GIF #2 — The product in action: agent runs `stash sessions search`, gets a cited answer -->

<p align="center">
  <img src="docs/assets/product.gif" alt="Stash in action — agent queries shared memory and gets cited answers" width="900" />
</p>

## How it works

- **Sessions stream in automatically.** A hook for your coding agent pushes every transcript — prompts, tool calls, artifacts — to a shared workspace.
- **Files and sessions live side by side.** Markdown, HTML, tables, PDFs. Humans and agents both write here; both sides see edits in real time.
- **Agents query it like a filesystem.** A CLI, MCP server, and virtual-filesystem shell expose the workspace to any agent. Semantic and keyword search across pages, sessions, and tables.
- **Stashes are the shareable slice.** Bundle pages and sessions into one link. Publish to the world, share with collaborators, or fork an external Stash into your own workspace.

## Why shared beats individual

When five engineers run Claude on the same repo, they generate valuable session transcripts. However, their coding agent can only access transcripts generated on the machine where the agent is currently running. As a result, engineering effort is duplicated and eng velocity is decreased. This is especially true as coding agents begin to run autonomously for significant periods of time. 

With Stash, every agent on the repo has context about every session created from that repo. Here are some use cases:

- **Code Faster / Don't Duplicate Work**: "Has anyone else tried fixing the memory leak in our API gateway? What was attempted?"
- **Look Organized During Standup**: "What did I get done this week? What other work did I do that isn't tracked in Git?"
- **Don't Be Blocked on Collaborators**: "Why did Sam increase the timeout to 30s? The git history is unhelpful."
- **Align With Your Team Faster**: "Please add a feedback endpoint to our API" -> Claude: "FYI, Sam decided not to add a feedback endpoint since we want to encourage churned users to hop on a call directly"

> "raw data from a given number of sources is collected, then compiled by an LLM into a .md knowledge base, then operated on by various CLIs by the LLM to do Q&A and to incrementally enhance it… **I think there is room here for an incredible new product instead of a hacky collection of scripts.**"
>
> — Andrej Karpathy, *LLM Knowledge Bases*

**Stash is that product.** A company brain humans and agents both write into — not a stack of shell scripts wrapped around a folder of markdown.

Built for —

| Use case | What teams put in it |
|---|---|
| **Engineering live docs** | coding-agent plans, ADRs, and design notes that stay current |
| **Company brain** | the shared context every agent and teammate reads from |
| **Research knowledge base** | long-running PKBs with sources, transcripts, and tables |
| **Ops playbooks** | release runbooks and on-call procedures |
| **Brand voice** | editorial guidelines and copy standards agents write to |
| **Personal knowledge management** | notes, drafts, and scratch files for a single operator |

## Quick Start

```bash
pip install stashai / uv tool install stashai
stash login
```

`stash login` walks you through account creation, picks a workspace, connects
your current repo when you want uploads, and wires up coding-agent plugins.
Use `stash connect` later when you are already authenticated and only need to
bind another repo to a workspace.

<details>
<summary>Prefer a one-liner?</summary>

```bash
bash -c "$(curl -fsSL https://joinstash.ai/install)"
```

The installer uses `uv` to install or update `stashai`, bootstrapping `uv`
when needed, and then runs `stash login`.
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
stash vfs "tree /workspaces -L 2"
stash vfs "find /workspaces -maxdepth 3 -type f | head -n 20"
stash vfs "rg \"database migration\" /workspaces"
```

## Integrations

Stash supports the following coding agents:
- **Claude Code** 
- **Cursor** 
- **Codex** 
- **OpenCode**
- **Gemini CLI**
- **Openclaw** 

Stash supports opt in per-coding agent. `stash login` can auto-install hooks for Claude Code, Cursor, Codex, and OpenCode; Gemini CLI and Openclaw are available in `plugins/` and are installed manually. Mix and match — different teammates can use different agents against the same shared brain.

## CLI Reference

See [here](https://www.joinstash.ai/docs/cli) for a CLI reference.

## Self-Hosted

Run Stash with prebuilt GHCR images:

For a local laptop dry run:

```bash
git clone https://github.com/Fergana-Labs/stash.git
cd stash
cp .env.example .env
docker compose -f docker-compose.prod.yml -f docker-compose.local.yml pull
docker compose -f docker-compose.prod.yml -f docker-compose.local.yml up -d
curl http://localhost:3456/health
open http://localhost:3457/login
```

For a public domain with Caddy and HTTPS:

```bash
# Set PUBLIC_URL and CORS_ORIGINS in .env, then replace app.example.com in Caddyfile.
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
curl https://app.example.com/health
```

Then install the CLI:

```bash
pip install stashai   # or: uv tool install stashai
cd /path/to/the/repo/you/want/to/connect
stash config base_url http://localhost:3456
stash login
```

Use your public URL instead of `http://localhost:3456` when connecting to a
domain-backed install:

```bash
stash config base_url https://app.example.com
```

Finally see it in action:

```
claude
> what did I get done last week? check stash.
```

## Privacy

Stash is built for engineering teams working in private repos.

- **LLM calls are optional and scoped.** When an Anthropic API key is configured, the server uses it for ask-the-workspace answers and auto-generated session titles. No key means those features are unavailable — the rest of Stash works without any LLM.
- **Permissioned workspaces.** Only invited members can access a workspace. Public visibility is controlled by Product Stashes.
- **Transcripts are opt-in.** If you don't want to share your agent transcripts, you can give your agent shared *read* access to the workspace's memory without uploading any of your own session data.
  
## FAQ

**What LLMs does Stash use?**
When an Anthropic API key is provided, the server calls Claude for ask-the-workspace (quality tier) and session title generation. Both are optional — without the key, Stash works but those features are disabled. There is no background page-writing agent.

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
