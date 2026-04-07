"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../../hooks/useAuth";

// --- Navigation structure ---

interface NavSection {
  title: string;
  items: { id: string; label: string }[];
}

const NAV: NavSection[] = [
  {
    title: "Getting Started",
    items: [
      { id: "overview", label: "Overview" },
      { id: "quickstart", label: "Quickstart" },
      { id: "concepts", label: "Concepts" },
    ],
  },
  {
    title: "Guides",
    items: [
      { id: "consume", label: "Consume" },
      { id: "curate", label: "Curate" },
      { id: "collaborate", label: "Collaborate" },
      { id: "workspaces", label: "Workspaces" },
    ],
  },
  {
    title: "Reference",
    items: [
      { id: "cli", label: "CLI" },
      { id: "mcp", label: "MCP Server" },
      { id: "api", label: "REST API" },
      { id: "webhooks", label: "Webhooks" },
    ],
  },
];

// --- Components ---

function Callout({ children, type = "info" }: { children: React.ReactNode; type?: "info" | "tip" | "warning" }) {
  const styles = {
    info: "border-l-brand bg-brand/5",
    tip: "border-l-green-500 bg-green-500/5",
    warning: "border-l-yellow-500 bg-yellow-500/5",
  };
  const icons = { info: "i", tip: "\u2713", warning: "!" };
  return (
    <div className={`border-l-4 rounded-r-lg px-4 py-3 my-4 ${styles[type]}`}>
      <div className="flex gap-2">
        <span className="text-sm font-bold opacity-60">{icons[type]}</span>
        <div className="text-sm text-dim">{children}</div>
      </div>
    </div>
  );
}

function CodeTabs({ tabs }: { tabs: { label: string; code: string }[] }) {
  const [active, setActive] = useState(0);
  return (
    <div className="my-4 rounded-lg border border-border overflow-hidden">
      <div className="flex bg-surface border-b border-border">
        {tabs.map((tab, i) => (
          <button
            key={tab.label}
            onClick={() => setActive(i)}
            className={`px-4 py-2 text-xs font-medium transition-colors ${
              i === active ? "text-foreground bg-base border-b-2 border-brand" : "text-muted hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <pre className="bg-base p-4 overflow-x-auto text-sm text-dim">
        <code>{tabs[active].code}</code>
      </pre>
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return <code className="bg-surface text-brand px-1.5 py-0.5 rounded text-[13px] font-mono">{children}</code>;
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="bg-base border border-border rounded-lg p-4 overflow-x-auto text-sm text-dim my-4 font-mono">
      <code>{children}</code>
    </pre>
  );
}

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="text-xl font-semibold text-foreground mt-10 mb-4 pb-2 border-b border-border scroll-mt-20 font-display">
      {children}
    </h2>
  );
}

function H3({ children }: { children: React.ReactNode }) {
  return <h3 className="text-base font-medium text-foreground mt-6 mb-2">{children}</h3>;
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-dim leading-relaxed mb-3">{children}</p>;
}

function ParamTable({ params }: { params: { name: string; type: string; desc: string; required?: boolean }[] }) {
  return (
    <div className="my-4 border border-border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-surface">
            <th className="text-left px-4 py-2 text-xs font-medium text-muted uppercase">Parameter</th>
            <th className="text-left px-4 py-2 text-xs font-medium text-muted uppercase">Type</th>
            <th className="text-left px-4 py-2 text-xs font-medium text-muted uppercase">Description</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p) => (
            <tr key={p.name} className="border-t border-border">
              <td className="px-4 py-2 font-mono text-foreground text-xs">
                {p.name}
                {p.required && <span className="text-red-400 ml-1">*</span>}
              </td>
              <td className="px-4 py-2 text-muted text-xs">{p.type}</td>
              <td className="px-4 py-2 text-dim text-xs">{p.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Main ---

export default function DocsPage() {
  const { user, logout } = useAuth();
  const [activeSection, setActiveSection] = useState("overview");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActiveSection(entry.target.id);
        }
      },
      { rootMargin: "-10% 0px -80% 0px" }
    );
    const ids = NAV.flatMap((s) => s.items.map((i) => i.id));
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <div className="h-screen flex flex-col bg-base">
      {/* Top bar */}
      <header className="h-14 flex items-center justify-between px-6 border-b border-border bg-surface flex-shrink-0">
        <div className="flex items-center gap-6">
          <Link href="/" className="text-lg font-bold font-display text-foreground tracking-tight">boozle</Link>
          <span className="text-xs text-muted font-medium uppercase tracking-wider">Documentation</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/" className="text-xs text-dim hover:text-foreground">Dashboard</Link>
          {user ? (
            <span className="text-xs text-muted">{user.display_name || user.name}</span>
          ) : (
            <Link href="/login" className="text-xs text-brand hover:text-brand-hover">Sign in</Link>
          )}
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside className="w-[220px] flex-shrink-0 border-r border-border overflow-y-auto py-4 bg-surface">
          {NAV.map((section) => (
            <div key={section.title} className="mb-4">
              <div className="px-4 py-1 text-[10px] font-semibold text-muted uppercase tracking-wider">
                {section.title}
              </div>
              {section.items.map((item) => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className={`block px-4 py-1.5 text-[13px] transition-colors border-l-2 ${
                    activeSection === item.id
                      ? "border-brand text-brand font-medium bg-brand/5"
                      : "border-transparent text-dim hover:text-foreground hover:border-border"
                  }`}
                >
                  {item.label}
                </a>
              ))}
            </div>
          ))}
        </aside>

        {/* Content */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-[720px] mx-auto px-8 py-8">

            {/* Overview */}
            <section id="overview" className="mb-16">
              <h1 className="text-3xl font-bold text-foreground font-display mb-2">Boozle</h1>
              <P>The auto-curating knowledge base for AI-augmented teams.</P>

              <Callout type="tip">
                <strong>New here?</strong> Start with the <a href="#quickstart" className="text-brand underline">Quickstart</a> — three commands to import your bookmarks and start searching.
              </Callout>

              <P>
                Throw in your bookmarks, Claude Code sessions, PDFs, YouTube videos, articles.
                A sleep agent curates it all into a searchable wiki with backlinks and semantic search.
              </P>

              <H3>Consume, Curate, Collaborate</H3>
              <div className="grid grid-cols-3 gap-3 my-4">
                {[
                  { title: "Consume", desc: "Throw stuff in. Bookmarks, files, agent history, structured data.", items: "Files, History, Tables", color: "border-brand/30" },
                  { title: "Curate", desc: "Sleep agent organizes data into a categorized wiki automatically.", items: "Notebooks, Personas", color: "border-green-500/30" },
                  { title: "Collaborate", desc: "Chat with your team. Create and share pages, reports.", items: "Chats, Pages", color: "border-violet-500/30" },
                ].map((c) => (
                  <div key={c.title} className={`border rounded-lg p-3 ${c.color}`}>
                    <div className="text-sm font-medium text-foreground mb-1">{c.title}</div>
                    <div className="text-xs text-dim leading-relaxed">{c.desc}</div>
                    <div className="text-[10px] text-muted mt-2 font-mono">{c.items}</div>
                  </div>
                ))}
              </div>

              <P>
                Everything lives in a <strong>workspace</strong> — a permissioned container where
                multiple agents and people collaborate.
              </P>
            </section>

            {/* Quickstart */}
            <section id="quickstart" className="mb-16">
              <H2 id="quickstart">Quickstart</H2>

              <H3>CLI</H3>
              <CodeTabs tabs={[
                { label: "pip", code: "pip install boozle\nboozle register yourname\nboozle import-bookmarks ~/Downloads/bookmarks.html" },
                { label: "Search", code: 'boozle search "that article about transformer architectures"' },
              ]} />
              <P>
                Your bookmarks are scraped (web articles, YouTube transcripts, PDFs) and stored as
                notebook pages. The sleep agent curates them into a categorized wiki overnight.
              </P>

              <H3>Claude Code (MCP)</H3>
              <CodeTabs tabs={[
                { label: "Setup", code: "claude mcp add boozle -- boozle mcp" },
                { label: "Environment", code: "export BOOZLE_API_KEY=your_api_key\nexport BOOZLE_URL=https://getboozle.com" },
              ]} />

              <Callout>
                Once connected, Claude Code can read and write to your knowledge base during sessions.
                Every conversation accumulates as searchable knowledge.
              </Callout>

              <H3>Web</H3>
              <P>
                Sign up at <a href="https://getboozle.com" className="text-brand underline">getboozle.com</a> and
                start using notebooks, search, and chats from the browser.
              </P>
            </section>

            {/* Concepts */}
            <section id="concepts" className="mb-16">
              <H2 id="concepts">Concepts</H2>

              <div className="space-y-4">
                {[
                  { name: "Workspace", badge: "Container", desc: "Top-level permissioned container. Members share all resources. Invite with a code." },
                  { name: "Files", badge: "Consume", desc: "Upload images, PDFs, documents to S3 storage. Attach to chat messages and notebook pages." },
                  { name: "History", badge: "Consume", desc: "Append-only event logs from agents. Tool calls, messages, sessions. Searchable via FTS and semantic search." },
                  { name: "Tables", badge: "Consume", desc: "Structured data with typed columns. Filters, views, CSV import/export. Optional row embeddings for semantic search." },
                  { name: "Notebooks", badge: "Curate", desc: "Wiki-style markdown pages with [[backlinks]], page graph, auto-index. Sleep agent writes here. Real-time collaborative editing." },
                  { name: "Personas", badge: "Curate", desc: "Sleep agent + notebook. Watches workspace histories (filtered by agent_name), curates into a personal wiki. Configurable sources, interval, model." },
                  { name: "Chats", badge: "Collaborate", desc: "Real-time messaging channels. Agents participate alongside humans. File attachments." },
                  { name: "Pages", badge: "Collaborate", desc: "HTML documents for shareable output — reports, slides, dashboards. Public sharing with analytics." },
                  { name: "Search", badge: "Cross-cutting", desc: "AI-powered universal search across notebooks, tables, history, and documents." },
                ].map((c) => (
                  <div key={c.name} className="flex gap-3 items-start">
                    <div className="w-24 flex-shrink-0">
                      <div className="text-sm font-medium text-foreground">{c.name}</div>
                      <div className="text-[10px] text-muted font-mono">{c.badge}</div>
                    </div>
                    <div className="text-sm text-dim leading-relaxed">{c.desc}</div>
                  </div>
                ))}
              </div>
            </section>

            {/* Consume */}
            <section id="consume" className="mb-16">
              <H2 id="consume">Consume</H2>
              <P>Getting data into Boozle. Zero-friction — data flows in automatically or with one command.</P>

              <H3>Import bookmarks</H3>
              <CodeBlock>{`boozle import-bookmarks bookmarks.html`}</CodeBlock>
              <P>
                Parses Chrome/Firefox exports. Scrapes each URL — articles via trafilatura,
                YouTube transcripts, PDF text extraction. Stores each as a notebook page.
              </P>
              <ParamTable params={[
                { name: "--notebook", type: "string", desc: 'Notebook name (default: "Bookmarks")' },
                { name: "--skip-scrape", type: "flag", desc: "Import titles + URLs only, skip content extraction" },
                { name: "--dry-run", type: "flag", desc: "Preview without importing" },
                { name: "--delay", type: "float", desc: "Seconds between scrape requests (default: 0.5)" },
              ]} />

              <H3>Push events via API</H3>
              <CodeTabs tabs={[
                { label: "curl", code: `curl -X POST https://getboozle.com/api/v1/memory/{store_id}/events \\\n  -H "Authorization: Bearer $API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"agent_name": "my-agent", "event_type": "tool_use", "content": "..."}'` },
                { label: "CLI", code: 'boozle history push "Searched for auth best practices" --agent my-agent --type tool_use' },
                { label: "MCP", code: "// Claude Code calls this automatically\npush_memory_event(workspace_id, store_id, ...)" },
              ]} />

              <H3>File uploads</H3>
              <P>
                Upload via REST API, the + button in chat, or the Image button in the notebook editor.
                Stored in S3-compatible storage (Cloudflare R2, AWS S3, MinIO).
              </P>
            </section>

            {/* Curate */}
            <section id="curate" className="mb-16">
              <H2 id="curate">Curate</H2>
              <P>The sleep agent turns raw data into structured knowledge.</P>

              <H3>Sleep agent</H3>
              <P>
                A background worker running every N minutes (configurable). It reads newly ingested
                data and calls Claude to organize it:
              </P>
              <ul className="list-disc list-inside text-sm text-dim mb-3 space-y-1 ml-1">
                <li>Creates <strong>category index pages</strong> with [[wiki links]]</li>
                <li>Writes <strong>content pages</strong> summarizing topics</li>
                <li>Creates <strong>pattern cards</strong> for recurring situations</li>
                <li>Organizes everything into <strong>folders</strong> by category</li>
                <li>Merges duplicates, deletes stale content</li>
              </ul>

              <Callout type="tip">
                Configure per-persona: which workspaces to watch, which agent names to filter by,
                curation interval, and LLM model. Access via Personas page or the API.
              </Callout>

              <H3>Wiki features</H3>
              <P>
                Notebook pages support <Code>{"[[Page Name]]"}</Code> wiki links with autocomplete.
                Backlinks appear at the bottom of each page. The page graph visualizes connections.
                Auto-index generates a table of contents.
              </P>

              <H3>Semantic search</H3>
              <P>
                Pages and table rows are embedded (OpenAI text-embedding-3-small).
                Search by meaning, not just keywords.
              </P>
            </section>

            {/* Collaborate */}
            <section id="collaborate" className="mb-16">
              <H2 id="collaborate">Collaborate</H2>

              <H3>Chats</H3>
              <P>
                Real-time messaging in workspace channels, personal rooms, or DMs.
                Agents participate as first-class members.
              </P>

              <H3>Pages</H3>
              <P>
                HTML/JS/CSS documents — slides, dashboards, reports. Agents generate these.
                Public sharing via token-based URLs with optional email/passcode gates and viewer analytics.
              </P>
            </section>

            {/* Workspaces */}
            <section id="workspaces" className="mb-16">
              <H2 id="workspaces">Workspaces</H2>
              <P>Permissioned container for teams. All resources are scoped to a workspace.</P>

              <H3>Roles</H3>
              <ParamTable params={[
                { name: "owner", type: "role", desc: "Full control. Can delete workspace." },
                { name: "admin", type: "role", desc: "Manage members, settings." },
                { name: "member", type: "role", desc: "Read/write all resources." },
              ]} />

              <H3>Object permissions</H3>
              <P>
                Individual objects can be set to <Code>inherit</Code> (workspace members),{" "}
                <Code>private</Code> (explicit shares only), or <Code>public</Code> (anyone reads).
              </P>
            </section>

            {/* CLI */}
            <section id="cli" className="mb-16">
              <H2 id="cli">CLI Reference</H2>
              <CodeBlock>{`pip install boozle`}</CodeBlock>

              <H3>Auth</H3>
              <CodeBlock>{`boozle register <name>                  # Create account (prompts for password)
boozle register <name> --type persona   # Create agent account
boozle login <name>                     # Login with password
boozle auth <url> --api-key <key>       # Auth with existing API key
boozle whoami                           # Show current user`}</CodeBlock>

              <H3>Import & Search</H3>
              <CodeBlock>{`boozle import-bookmarks <file.html>     # Import Chrome/Firefox bookmarks
boozle search <query>                   # Universal search across all data`}</CodeBlock>

              <H3>Resources</H3>
              <CodeBlock>{`boozle notebooks list [--ws ID] [--all]
boozle notebooks create <name>
boozle notebooks add-page <nb_id> <name> --content "..."
boozle history push <content> [--store ID] [--agent cli]
boozle history search <query> [--store ID]
boozle tables list [--ws ID]`}</CodeBlock>

              <P>Run <Code>boozle --help</Code> for the complete command list.</P>
            </section>

            {/* MCP */}
            <section id="mcp" className="mb-16">
              <H2 id="mcp">MCP Server</H2>
              <P>30+ tools via the Model Context Protocol for any MCP-compatible AI agent.</P>

              <CodeBlock>{`claude mcp add boozle -- boozle mcp`}</CodeBlock>

              <H3>Tools by category</H3>
              <div className="space-y-2 my-4">
                {[
                  { cat: "Auth", tools: "register, whoami, update_profile" },
                  { cat: "Workspaces", tools: "create, list, join, info, members" },
                  { cat: "Notebooks", tools: "create, read, update, delete, backlinks, outlinks, page_graph, semantic_search_pages, auto_index" },
                  { cat: "Files", tools: "upload, list, get_url, delete" },
                  { cat: "Tables", tools: "full CRUD + configure_embeddings, backfill, semantic_search_rows" },
                  { cat: "History", tools: "push_event, query, search, query_history (LLM synthesis)" },
                  { cat: "Search", tools: "universal_search across all resources" },
                  { cat: "Sleep Agent", tools: "get_config, configure, trigger" },
                  { cat: "Chats", tools: "create, send, read, search" },
                ].map((c) => (
                  <div key={c.cat} className="flex gap-3 text-sm">
                    <span className="w-24 flex-shrink-0 font-medium text-foreground">{c.cat}</span>
                    <span className="text-dim font-mono text-xs">{c.tools}</span>
                  </div>
                ))}
              </div>
            </section>

            {/* API */}
            <section id="api" className="mb-16">
              <H2 id="api">REST API</H2>
              <P>
                Base URL: <Code>https://getboozle.com/api/v1/</Code>
                <br />Auth: <Code>{"Authorization: Bearer <api_key>"}</Code>
              </P>

              <H3>Key endpoints</H3>
              <CodeBlock>{`POST   /users/register                              # Create account
POST   /users/login                                 # Login

POST   /workspaces                                  # Create workspace
GET    /workspaces/mine                             # List my workspaces

POST   /workspaces/{ws}/notebooks                   # Create notebook
POST   /workspaces/{ws}/notebooks/{nb}/pages        # Create page
GET    /workspaces/{ws}/notebooks/{nb}/graph         # Page graph
GET    /workspaces/{ws}/notebooks/{nb}/pages/semantic-search?q=...

POST   /workspaces/{ws}/memory/{store}/events        # Push history event
GET    /workspaces/{ws}/memory/{store}/events/search?q=...

POST   /workspaces/{ws}/search                       # Universal search
POST   /me/search                                    # Personal search

POST   /workspaces/{ws}/files                        # Upload file (multipart)
POST   /workspaces/{ws}/tables/{tbl}/rows            # Create table row`}</CodeBlock>

              <P>Personal variants (no workspace) exist for all endpoints.</P>
            </section>

            {/* Webhooks */}
            <section id="webhooks" className="mb-16">
              <H2 id="webhooks">Webhooks</H2>
              <P>Subscribe to workspace events. HMAC-SHA256 signed delivery.</P>

              <H3>Event types</H3>
              <ParamTable params={[
                { name: "chat.message", type: "event", desc: "New message in a chat" },
                { name: "memory.event", type: "event", desc: "New history event pushed" },
                { name: "table.row_created", type: "event", desc: "Table row created" },
                { name: "table.row_updated", type: "event", desc: "Table row updated" },
                { name: "table.row_deleted", type: "event", desc: "Table row deleted" },
              ]} />

              <H3>Setup</H3>
              <CodeBlock>{`POST /workspaces/{ws}/webhooks
{
  "url": "https://your-server.com/webhook",
  "secret": "optional-hmac-secret",
  "event_filter": ["table.row_created", "chat.message"]
}`}</CodeBlock>
            </section>

          </div>
        </main>
      </div>
    </div>
  );
}
