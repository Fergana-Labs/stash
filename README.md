
<p align="center">
  <a href="https://joinstash.ai"><img src="docs/assets/logo.svg" alt="Stash" width="320" /></a>
</p>

<h3 align="center">Your team's AI work, compounding.</h3>

<p align="center">
  Stash is a CLI to search over your team's coding agent sessions. <br> It captures every coding-agent run across your team and turns <br> it into a shared, evolving asset every agent can build on.
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
  <img src="docs/assets/visualizations.gif" alt="Stash visualizations — embedding space, page graph, agent activity" width="900" />
</p>
<!-- GIF #2 — The product in action: agent runs `stash history search`, gets a cited answer -->

<p align="center">
  <img src="docs/assets/product.gif" alt="Stash in action — agent queries shared memory and gets cited answers" width="900" />
</p>

## How it works

- Stash installs a hook for your coding agents that automatically uploads session transcripts to a shared store.
- Then, it exposes a CLI that allows you and your teammates to query this shared store.
- It automatically builds a [Karpathy-style wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) on top of the set of session transcripts to make it easier for your coding agents to query its contents.

## Why shared beats individual

When five engineers run Claude on the same repo, they generate valuable session transcripts. However, their coding agent can only access transcripts generated on the machine where the agent is currently running. As a result, engineering effort is duplicated and eng velocity is decreased. This is especially true as coding agents begin to run autonomously for significant periods of time. 

With Stash, every agent on the repo has context about every session created from that repo. Here are some use cases:

- **Code Faster / Don't Duplicate Work**: "Has anyone else tried fixing the memory leak in our API gateway? What was attempted?"
- **Look Organized During Standup**: "What did I get done this week? What other work did I do that isn't tracked in Git?"
- **Don't Be Blocked on Collaborators**: "Why did Sam increase the timeout to 30s? The git history is unhelpful."
- **Align With Your Team Faster**: "Please add a feedback endpoint to our API" -> Claude: "FYI, Sam decided not to add a feedback endpoint since we want to encourage churned users to hop on a call directly"

> "raw data from a given number of sources is collected, then compiled by an LLM into a .md wiki, then operated on by various CLIs by the LLM to do Q&A and to incrementally enhance the wiki… **I think there is room here for an incredible new product instead of a hacky collection of scripts.**"
>
> — Andrej Karpathy, *LLM Knowledge Bases*

**Stash is that product. For teams of coding agents working on the same repo.** Your agents' streamed sessions are the raw data. The wiki is curated automatically by our sleep agent. Everything lands in one workspace your whole team can query. AI usage becomes a shared, evolving asset, not individual effort.

## Quick Start

Run this in a terminal:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"
```

<p align="center">
  <img src="docs/assets/welcome.png" alt="Stash welcome screen after install" width="900" />
</p>

Then try it: ask your coding agent if it has access to Stash.

<p align="center">
  <img src="docs/assets/agent-access.png" alt="Coding agent confirming access to the Stash CLI" width="900" />
</p>

## Integrations

Stash supports the following coding agents:
- **Claude Code** 
- **Cursor** 
- **Codex** 
- **OpenCode**
- **Gemini CLI**
- **Openclaw** 

Stash supports opt in per-coding agent. Mix and match — different teammates can use different agents against the same shared brain.

## CLI Reference

See [here](https://www.joinstash.ai/docs/cli) for a CLI reference.

## Self-Hosted

To self host, just run docker compose on infrastructure of your choice.

```bash
git clone https://github.com/Fergana-Labs/stash.git
cd stash
cp .env.example .env          # fill in credentials + API keys
# edit Caddyfile → replace app.example.com with your domain
docker compose -f docker-compose.prod.yml up -d
```
Set `EMBEDDING_PROVIDER` to use a third-party embedding provider (otherwise we'll just use local `sentence-transformers`). Set `S3_ENDPOINT`, `S3_BUCKET`, and `S3_ACCESS_KEY` to use S3-compatible object storage (R2, S3, MinIO) for file uploads.

> Local development? Use `docker compose up -d` (no `-f` flag) — simple setup with hardcoded dev credentials.

## Privacy

Stash is built for engineering teams working in private repos.

- **No LLM calls from the server.** Curation and search run inside your agent (Claude Code, Cursor, etc.) using the keys it already has. The Stash backend itself makes no model calls.
- **Permissioned workspaces.** Only invited members can access a workspace. Public visibility is per-resource.
- **Transcripts are opt-in.** If you don't want to share your agent trasncripts, you can give your agent shared *read* access to the workspace's memory without uploading any of your own session data.
  
## FAQ

**What LLMs does Stash use?**
None on the server. Your coding agent is responsible for curation of the knowledge base that gets built on top of uploaded transcripts. There's a hook that's debounced to run at most once every 24 hours which asks your coding agent to look through the knowledge base and add new information, remove duplicates, etc. 

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
