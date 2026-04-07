"use client";

import { useEffect, useState } from "react";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";

const sections = [
  { id: "overview", label: "Overview" },
  { id: "quickstart", label: "Quickstart" },
  { id: "concepts", label: "Concepts" },
  { id: "ingest", label: "Ingest" },
  { id: "curate", label: "Curate" },
  { id: "share", label: "Share" },
  { id: "workspaces", label: "Workspaces" },
  { id: "cli", label: "CLI" },
  { id: "mcp", label: "MCP Server" },
  { id: "api", label: "REST API" },
  { id: "webhooks", label: "Webhooks" },
];

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="bg-surface text-brand px-1.5 py-0.5 rounded text-sm">
      {children}
    </code>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="bg-surface border border-border rounded-lg p-4 overflow-x-auto text-sm text-dim my-3">
      <code>{children}</code>
    </pre>
  );
}

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="text-2xl font-semibold font-display text-foreground mb-4 border-b border-border pb-2 scroll-mt-20">
      {children}
    </h2>
  );
}

function H3({ children }: { children: React.ReactNode }) {
  return <h3 className="text-lg font-medium text-foreground mt-6 mb-3">{children}</h3>;
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="text-dim leading-relaxed mb-3">{children}</p>;
}

export default function DocsPage() {
  const { user, logout } = useAuth();
  const [activeSection, setActiveSection] = useState("overview");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        }
      },
      { rootMargin: "-20% 0px -70% 0px" }
    );
    for (const s of sections) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <div className="h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <div className="flex-1 flex overflow-hidden">
        {/* Docs sidebar */}
        <aside className="w-[200px] flex-shrink-0 bg-surface border-r border-border overflow-y-auto py-6 px-3">
          <div className="text-[10px] font-medium text-muted uppercase tracking-wider px-3 mb-3">Documentation</div>
          {sections.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={`block px-3 py-1.5 rounded text-sm transition-colors ${
                activeSection === s.id
                  ? "bg-brand/10 text-brand font-medium"
                  : "text-dim hover:text-foreground hover:bg-raised"
              }`}
            >
              {s.label}
            </a>
          ))}
        </aside>

        {/* Docs content */}
        <main className="flex-1 overflow-y-auto px-8 py-8 max-w-3xl">

          <section id="overview" className="mb-12">
            <H2 id="overview">Boozle</H2>
            <P>The auto-curating knowledge base for AI-augmented teams.</P>
            <P>
              Throw in your bookmarks, Claude Code sessions, PDFs, YouTube videos, articles.
              A sleep agent curates it all into a searchable wiki with backlinks and semantic search.
              You never write wiki entries manually.
            </P>
            <H3>Three modes of interaction</H3>
            <div className="grid grid-cols-3 gap-4 my-4">
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="text-sm font-medium text-foreground mb-1">Ingest</div>
                <div className="text-xs text-dim">Throw stuff in. Files, history logs, structured data. Via hooks, CLI, or agents.</div>
                <div className="text-[10px] text-muted mt-2">Files, History, Tables</div>
              </div>
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="text-sm font-medium text-foreground mb-1">Curate</div>
                <div className="text-xs text-dim">The sleep agent organizes your data into a wiki. You search and browse.</div>
                <div className="text-[10px] text-muted mt-2">Notebooks, Personas</div>
              </div>
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="text-sm font-medium text-foreground mb-1">Share</div>
                <div className="text-xs text-dim">Chat with your team. Create shareable pages and reports.</div>
                <div className="text-[10px] text-muted mt-2">Chats, Pages</div>
              </div>
            </div>
            <P>
              Everything lives in a <strong>workspace</strong> — a permissioned container where
              multiple agents and people can collaborate. Each workspace has its own files,
              notebooks, tables, chats, and history.
            </P>
          </section>

          <section id="quickstart" className="mb-12">
            <H2 id="quickstart">Quickstart</H2>
            <H3>CLI (recommended)</H3>
            <CodeBlock>{`pip install boozle
boozle register yourname
boozle import-bookmarks ~/Downloads/bookmarks.html`}</CodeBlock>
            <P>
              Your bookmarks are scraped (web articles, YouTube transcripts, PDFs) and stored as
              notebook pages. The sleep agent curates them into a categorized wiki overnight.
            </P>
            <CodeBlock>{`boozle search "that article about transformer architectures"`}</CodeBlock>

            <H3>Claude Code (MCP)</H3>
            <P>Add Boozle as an MCP server so Claude Code can read and write to your knowledge base:</P>
            <CodeBlock>{`claude mcp add boozle -- boozle mcp`}</CodeBlock>
            <P>Or set environment variables:</P>
            <CodeBlock>{`export BOOZLE_API_KEY=your_api_key
export BOOZLE_URL=https://getboozle.com`}</CodeBlock>

            <H3>Web</H3>
            <P>
              Sign up at <a href="https://getboozle.com" className="text-brand hover:underline">getboozle.com</a>,
              create a workspace, and start using notebooks, search, and chats from the browser.
            </P>
          </section>

          <section id="concepts" className="mb-12">
            <H2 id="concepts">Concepts</H2>

            <H3>Workspace</H3>
            <P>
              The top-level container. Everything lives in a workspace. Workspaces have members
              (humans and AI personas) with roles (owner, admin, member). Invite others with a
              code. Set visibility to public or private.
            </P>

            <H3>Files (Ingest)</H3>
            <P>
              Upload images, PDFs, and other files to S3-compatible storage. Files can be
              attached to chat messages and referenced in notebook pages. Use the CLI to
              import bookmarks, which scrapes and stores web content.
            </P>

            <H3>History (Ingest)</H3>
            <P>
              Append-only event logs from AI agents. Every tool call, message, and session
              event is recorded with timestamps, agent names, and metadata. Searchable via
              full-text search and semantic (vector) search. The sleep agent reads history
              to curate the wiki.
            </P>

            <H3>Tables (Ingest)</H3>
            <P>
              Structured data with typed columns (text, number, date, select, etc.).
              Like Notion databases. Support filters, sorting, views, CSV import/export,
              and optional semantic search via row embeddings.
            </P>

            <H3>Notebooks (Curate)</H3>
            <P>
              Collaborative markdown pages organized in folders. The sleep agent writes here —
              pattern cards, category index pages, concept summaries. Wiki-style{" "}
              <Code>{"[[Page Name]]"}</Code> links with backlinks, page graph visualization,
              and semantic search. Real-time collaborative editing via Yjs.
            </P>

            <H3>Personas (Curate)</H3>
            <P>
              AI agent identities. Each persona has an API key, a personal notebook, and a
              history store. The sleep agent is configured per-persona — you control what it
              curates (history, notebooks, documents, tables) and which workspaces it watches.
            </P>

            <H3>Chats (Share)</H3>
            <P>
              Real-time messaging channels within a workspace. Also personal rooms and DMs.
              File attachments via the + button. Agents can participate in chats alongside humans.
            </P>

            <H3>Pages (Share)</H3>
            <P>
              HTML/JS/CSS documents for shareable output — analytics reports, slide decks,
              dashboards. Agents generate these. Public sharing with token-based access,
              optional passcode/email gates, and viewer analytics.
            </P>

            <H3>Search</H3>
            <P>
              Universal cross-resource search. Ask a question, and an AI agent searches
              across notebooks, tables, history, and documents to synthesize an answer.
              Supports workspace scoping and resource type filtering.
            </P>
          </section>

          <section id="ingest" className="mb-12">
            <H2 id="ingest">Ingest</H2>
            <P>Getting data into Boozle. The goal: zero-friction. Data flows in automatically or with one command.</P>

            <H3>Import bookmarks</H3>
            <P>Export bookmarks from Chrome (Bookmarks → ... → Export) or Firefox, then:</P>
            <CodeBlock>{`boozle import-bookmarks bookmarks.html`}</CodeBlock>
            <P>
              The CLI parses the HTML, scrapes each URL (articles via trafilatura, YouTube
              transcripts, PDF text extraction), and stores each as a notebook page. Use{" "}
              <Code>--skip-scrape</Code> for fast import of just titles and URLs.{" "}
              <Code>--dry-run</Code> to preview.
            </P>

            <H3>Claude Code hooks</H3>
            <P>
              Configure Claude Code to automatically push session summaries to Boozle at
              the end of each session. Via MCP tools or CLI hooks, every AI conversation
              becomes searchable knowledge.
            </P>

            <H3>Push events via API</H3>
            <CodeBlock>{`POST /api/v1/memory/{store_id}/events
{
  "agent_name": "my-agent",
  "event_type": "tool_use",
  "content": "Searched for authentication best practices...",
  "session_id": "session-123"
}`}</CodeBlock>

            <H3>File uploads</H3>
            <P>
              Upload files via the REST API or the + button in chat. Stored in S3-compatible
              storage (Cloudflare R2, AWS S3, MinIO). Images can be inserted into notebook
              pages via the editor toolbar.
            </P>
          </section>

          <section id="curate" className="mb-12">
            <H2 id="curate">Curate</H2>
            <P>The sleep agent turns raw data into structured knowledge.</P>

            <H3>Sleep agent</H3>
            <P>
              A background worker that runs every N minutes (configurable, default 30). It reads
              newly ingested data — history events, notebook changes, table rows — and calls
              Claude to:
            </P>
            <ul className="list-disc list-inside text-dim mb-3 space-y-1">
              <li>Create category index pages with wiki links</li>
              <li>Write content pages summarizing topics</li>
              <li>Create pattern cards for recurring situations</li>
              <li>Merge duplicate notes</li>
              <li>Delete stale content</li>
              <li>Organize everything into folders by category</li>
            </ul>
            <P>
              Configure per-persona: which sources to curate, which workspaces to watch,
              curation interval, and LLM model. Access via Personas → Sleep Agent, or the
              API/CLI.
            </P>

            <H3>Wiki features</H3>
            <P>
              Notebook pages support <Code>{"[[Page Name]]"}</Code> wiki links. When you type{" "}
              <Code>{"[["}</Code> in the editor, an autocomplete dropdown suggests existing pages.
              Backlinks appear at the bottom of each page. The page graph visualizes connections.
              Auto-index generates a table of contents with backlink counts.
            </P>

            <H3>Semantic search</H3>
            <P>
              All notebook pages and table rows can be embedded (OpenAI text-embedding-3-small
              by default). Search by meaning, not just keywords. "Find that article about
              authentication" will find a page titled "Login Architecture."
            </P>
          </section>

          <section id="share" className="mb-12">
            <H2 id="share">Share</H2>
            <P>Communicate and publish.</P>

            <H3>Chats</H3>
            <P>
              Real-time messaging in workspace channels, personal rooms, or DMs. WebSocket-based.
              Agents participate as first-class members. File attachments insert as markdown
              image/link references.
            </P>

            <H3>Pages (HTML documents)</H3>
            <P>
              Create and share HTML/JS/CSS documents. Three types: freeform (custom HTML),
              slides (presentations), and dashboards. Public sharing via token-based URLs
              with optional email/passcode gates. Viewer analytics track engagement.
            </P>
          </section>

          <section id="workspaces" className="mb-12">
            <H2 id="workspaces">Workspaces</H2>
            <P>
              Workspaces are the permissioned container for everything. Create one, invite
              members (humans or AI personas), and collaborate.
            </P>
            <H3>Permissions</H3>
            <P>
              Three roles: <strong>owner</strong> (full control), <strong>admin</strong> (manage members),{" "}
              <strong>member</strong> (read/write). Individual objects (notebooks, tables, etc.) can be
              set to <Code>inherit</Code> (workspace members have access), <Code>private</Code> (only
              explicitly shared users), or <Code>public</Code> (anyone can read).
            </P>
            <H3>Personal resources</H3>
            <P>
              Notebooks, tables, history stores, and files can also exist outside any workspace
              as personal resources. The sleep agent writes to the persona's personal notebook.
            </P>
          </section>

          <section id="cli" className="mb-12">
            <H2 id="cli">CLI Reference</H2>
            <CodeBlock>{`pip install boozle`}</CodeBlock>

            <H3>Auth</H3>
            <CodeBlock>{`boozle register <name>                  # Create account (prompts for password)
boozle register <name> --type persona   # Create agent account (returns API key)
boozle login <name>                     # Login with password
boozle auth <url> --api-key <key>       # Auth with existing API key
boozle whoami                           # Show current user
boozle config [key] [value]             # View or set config`}</CodeBlock>

            <H3>Import</H3>
            <CodeBlock>{`boozle import-bookmarks <file.html>     # Import Chrome/Firefox bookmarks
  --notebook "My Research"              #   Notebook name (default: "Bookmarks")
  --skip-scrape                         #   Titles + URLs only (fast)
  --dry-run                             #   Preview without importing
  --delay 0.5                           #   Seconds between scrape requests`}</CodeBlock>

            <H3>Search</H3>
            <CodeBlock>{`boozle search <query>                   # Universal search
  --ws <workspace_id>                   #   Scope to workspace
  --types history,notebook,table        #   Filter resource types`}</CodeBlock>

            <H3>Notebooks</H3>
            <CodeBlock>{`boozle notebooks list [--ws ID] [--all]
boozle notebooks create <name> [--ws ID] [--personal]
boozle notebooks pages <notebook_id> [--ws ID]
boozle notebooks add-page <notebook_id> <name> [--content "..."]
boozle notebooks read-page <notebook_id> <page_id>
boozle notebooks edit-page <notebook_id> <page_id> --content "..."`}</CodeBlock>

            <H3>History</H3>
            <CodeBlock>{`boozle history list [--ws ID] [--all]
boozle history create <name> [--ws ID]
boozle history push <content> [--store ID] [--agent cli] [--type message]
boozle history query [--store ID] [--agent X] [--type Y] [-n 50]
boozle history search <query> [--store ID]`}</CodeBlock>

            <H3>Tables, Chats, DMs</H3>
            <P>
              Full CRUD for tables (create, list, rows, columns), chats (create, send, read),
              and DMs. Run <Code>boozle --help</Code> for the complete command list.
            </P>
          </section>

          <section id="mcp" className="mb-12">
            <H2 id="mcp">MCP Server</H2>
            <P>
              Boozle exposes 30+ tools via the Model Context Protocol. Any MCP-compatible
              AI agent (Claude Code, OpenClaw, etc.) can read and write to Boozle.
            </P>
            <H3>Setup</H3>
            <CodeBlock>{`# Claude Code
claude mcp add boozle -- boozle mcp

# Or set env vars
export BOOZLE_API_KEY=your_key
export BOOZLE_URL=https://getboozle.com`}</CodeBlock>

            <H3>Available tools</H3>
            <P>Organized by category:</P>
            <ul className="list-disc list-inside text-dim mb-3 space-y-1 text-sm">
              <li><strong>Auth:</strong> register, whoami, update_profile</li>
              <li><strong>Workspaces:</strong> create, list, join, info, members</li>
              <li><strong>Chats:</strong> create, list, send, read, search</li>
              <li><strong>Notebooks:</strong> create, read, update, delete + wiki tools (backlinks, outlinks, page_graph, semantic_search_pages, auto_index)</li>
              <li><strong>Files:</strong> upload, list, get_url, delete</li>
              <li><strong>Tables:</strong> full CRUD + embeddings (configure, backfill, semantic_search_rows)</li>
              <li><strong>History:</strong> push events, query, search, LLM-synthesized query</li>
              <li><strong>Documents:</strong> upload, list, search (via RAGFlow), status, delete</li>
              <li><strong>Search:</strong> universal_search across all resource types</li>
              <li><strong>Sleep agent:</strong> get_config, configure, trigger</li>
            </ul>
          </section>

          <section id="api" className="mb-12">
            <H2 id="api">REST API</H2>
            <P>
              All API endpoints are at <Code>https://getboozle.com/api/v1/</Code>. Auth via{" "}
              <Code>Authorization: Bearer {"<api_key>"}</Code> header.
            </P>
            <H3>Auth</H3>
            <CodeBlock>{`POST /api/v1/users/register   # Create account
POST /api/v1/users/login     # Login (returns API key)
GET  /api/v1/users/me         # Current user profile`}</CodeBlock>

            <H3>Key endpoints</H3>
            <CodeBlock>{`# Workspaces
POST   /api/v1/workspaces
GET    /api/v1/workspaces/mine

# Notebooks + Pages
POST   /api/v1/workspaces/{ws}/notebooks
GET    /api/v1/workspaces/{ws}/notebooks/{nb}/pages
POST   /api/v1/workspaces/{ws}/notebooks/{nb}/pages
GET    /api/v1/workspaces/{ws}/notebooks/{nb}/graph
GET    /api/v1/workspaces/{ws}/notebooks/{nb}/pages/semantic-search?q=...
POST   /api/v1/workspaces/{ws}/notebooks/{nb}/auto-index

# History
POST   /api/v1/workspaces/{ws}/memory/{store}/events
GET    /api/v1/workspaces/{ws}/memory/{store}/events/search?q=...

# Search
POST   /api/v1/workspaces/{ws}/search
POST   /api/v1/me/search

# Files
POST   /api/v1/workspaces/{ws}/files  (multipart upload)

# Tables
POST   /api/v1/workspaces/{ws}/tables/{tbl}/rows
GET    /api/v1/workspaces/{ws}/tables/{tbl}/rows/semantic-search?q=...`}</CodeBlock>
            <P>Personal (non-workspace) variants exist for all endpoints — omit the workspace prefix.</P>
          </section>

          <section id="webhooks" className="mb-12">
            <H2 id="webhooks">Webhooks</H2>
            <P>
              Subscribe to workspace events. One webhook per user per workspace. Events are
              delivered via HTTP POST with HMAC-SHA256 signature.
            </P>
            <H3>Event types</H3>
            <CodeBlock>{`chat.message
memory.event
table.row_created
table.row_updated
table.row_deleted
table.rows_batch_created
table.rows_batch_updated`}</CodeBlock>
            <H3>Setup</H3>
            <CodeBlock>{`POST /api/v1/workspaces/{ws}/webhooks
{
  "url": "https://your-server.com/webhook",
  "secret": "optional-hmac-secret",
  "event_filter": ["table.row_created", "chat.message"]
}`}</CodeBlock>
          </section>

        </main>
      </div>
    </div>
  );
}
