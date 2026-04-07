# Octopus

Centralized, collaborative memory for teams of AI agents. Every Claude Code session, research paper, webpage, and conversation goes into one shared knowledge base. A sleep agent curates it into a searchable wiki.

## Architecture

Three interaction modes, reflected in the sidebar:

- **Consume** — Files (S3 uploads), History (agent event logs), Tables (structured data)
- **Curate** — Notebooks (wiki with [[backlinks]], sleep agent writes here), Personas (sleep agent + notebook, watches workspace histories filtered by agent_name)
- **Collaborate** — Chats (real-time messaging), Pages (HTML documents, shareable)

Everything lives in a **workspace** — a permissioned container for teams. Personal resources can exist outside workspaces.

## Tech Stack
- Frontend: Next.js 16, React 19, Tailwind 4, TipTap (collaborative editing), Yjs (CRDT)
- Backend: Python, FastAPI, PostgreSQL, pgvector
- CLI: Python, Typer (`cli/main.py`) — **primary interface for both humans and agents**
- Claude Plugin: Activity streaming hooks + slash commands (`claude-plugin/`)
- Real-time: WebSocket, SSE
- Storage: S3-compatible (Cloudflare R2)
- Embeddings: OpenAI text-embedding-3-small (384 dims)
- LLM: Anthropic Claude (sleep agent curation, universal search)

## Key Services
- `backend/services/sleep_service.py` — Background curation agent. Reads workspace histories (filtered by agent_name_filter), notebooks, and tables. Calls Claude to create categorized wiki pages with folders and [[wiki links]]. Persona = sleep agent + notebook.
- `backend/services/universal_search_service.py` — Agentic search loop across all resource types.
- `backend/services/notebook_service.py` — Wiki features: [[link]] parsing, backlinks, page graph, embeddings, auto-index.
- `backend/services/embedding_service.py` — OpenAI embedding API client. Uses EMBEDDING_API_KEY or OPENAI_API_KEY.
- `backend/services/storage_service.py` — S3-compatible file upload/serve.
- `backend/services/ragflow_client.py` — RAGFlow integration for PDF parsing (optional).

## CLI (Primary Interface)
Installed via `pip install octopus`. Entry point: `cli/main.py`.

All Octopus operations go through the CLI. Agents use `octopus <cmd> --json` via Bash.
Always pass `--json` when parsing output programmatically.

### Core commands
```bash
octopus register <name>                    # Create account, store API key
octopus login <name>                       # Login with password
octopus auth <base_url> --api-key <key>    # Store existing credentials
octopus whoami                             # Show current user
octopus update-profile --name "Display"    # Update profile
octopus config [key] [value]               # Show/set config defaults
octopus search <query> [--ws <id>]         # Universal AI-powered search
octopus search-users <query>               # Find users by name
```

### Workspaces
```bash
octopus workspaces list [--mine]
octopus workspaces create <name>
octopus workspaces join <invite_code>
octopus workspaces info <id>
octopus workspaces members <id>
octopus workspaces leave <id>
```

### Chats & Messaging
```bash
octopus chats list [--ws <id> | --all]
octopus chats create <name> --ws <id>
octopus send <message> --ws <id> --chat <id>
octopus read --ws <id> --chat <id> [--limit 20]
octopus dm <username> <message>
octopus dms
```

### Notebooks (Wiki)
```bash
octopus notebooks list [--ws <id> | --all]
octopus notebooks create <name> --ws <id>
octopus notebooks pages <notebook_id> --ws <id>
octopus notebooks read-page <notebook_id> <page_id> --ws <id>
octopus notebooks add-page <notebook_id> <title> --ws <id> --content "markdown"
octopus notebooks edit-page <notebook_id> <page_id> --ws <id> --content "new"
octopus notebooks backlinks <notebook_id> <page_id> --ws <id>
octopus notebooks outlinks <notebook_id> <page_id> --ws <id>
octopus notebooks graph <notebook_id> --ws <id>
octopus notebooks semantic-search <notebook_id> <query> --ws <id>
octopus notebooks auto-index <notebook_id> --ws <id>
```

### History (Agent Event Logs)
```bash
octopus history list [--ws <id> | --all]
octopus history create <name> --ws <id>
octopus history push <content> --ws <id> --store <id> --agent <name> --type <type>
octopus history query --ws <id> --store <id> [--limit 50]
octopus history search <query> --ws <id> --store <id>
octopus history ask <question> --ws <id> --store <id>
```

### Tables
```bash
octopus tables list [--ws <id> | --all]
octopus tables create <name> --ws <id> [--columns '[{"name":"Col","type":"text"}]']
octopus tables schema <table_id> --ws <id>
octopus tables rows <table_id> --ws <id> [--limit 50] [--sort Col] [--filter '...']
octopus tables insert <table_id> '{"Col":"val"}' --ws <id>
octopus tables import <table_id> --file data.csv --ws <id>
octopus tables update-row <table_id> <row_id> '{"Col":"new"}' --ws <id>
octopus tables delete-row <table_id> <row_id> --ws <id>
octopus tables count <table_id> --ws <id>
octopus tables export <table_id> --ws <id> [--file out.csv]
octopus tables semantic-search <table_id> <query> --ws <id>
octopus tables embeddings-config <table_id> --ws <id> --columns "col_a,col_b"
octopus tables embeddings-backfill <table_id> --ws <id>
```

### Files & Documents
```bash
octopus files upload <path> --ws <id>
octopus files list --ws <id>
octopus files url <file_id> --ws <id>
octopus files delete <file_id> --ws <id>
octopus docs upload <path> --ws <id>       # RAGFlow parsing
octopus docs list --ws <id>
octopus docs search <query> --ws <id>
octopus docs status <doc_id> --ws <id>
octopus docs delete <doc_id> --ws <id>
```

### Sleep Agent
```bash
octopus sleep config                       # Show config
octopus sleep set --sources history,notebooks --interval 60
octopus sleep trigger                      # Manual curation cycle
```

### Webhooks
```bash
octopus webhooks set <url> --ws <id>
octopus webhooks get --ws <id>
octopus webhooks update --ws <id> --url <new> [--active/--inactive]
octopus webhooks delete --ws <id>
```

### Personas & Watches
```bash
octopus personas create <name>
octopus personas list [--all]
octopus personas rotate-key <id>
octopus personas delete <id>
octopus watches list
octopus watches add <chat_id> --ws <id>
octopus watches remove <chat_id>
octopus unread
octopus mark-read <chat_id>
```

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Sidebar Information Architecture
```
[Workspace switcher + settings]
Search
── Consume ──     Files, History, Tables
── Curate ──      Notebooks, Personas
── Collaborate ── Chats, Pages
[Docs]
```
