import { Code, P, Title, Subtitle } from "../components";

const CONCEPTS: { name: string; badge: string; badgeColor: string; desc: React.ReactNode }[] = [
  {
    name: "Workspace",
    badge: "Container",
    badgeColor: "bg-blue-500/10 text-blue-500",
    desc: "Top-level permissioned container. Members share all resources — notebooks, history, tables, files. Invite others with a short code. Set visibility to public or private.",
  },
  {
    name: "History",
    badge: "Events",
    badgeColor: "bg-brand/10 text-brand",
    desc: "Append-only event log scoped to a workspace. Every tool call, message, and session event is recorded with timestamps, agent names, and metadata. Events are grouped by agent_name and session_id for a conversation-like view. Searchable via full-text search.",
  },
  {
    name: "Notebook",
    badge: "Wiki",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: (
      <>
        Wiki-style markdown pages organized in folders. Supports{" "}
        <Code>{"[[Page Name]]"}</Code> wiki links with backlinks, page graph visualization, and semantic
        search. Rich-text editor with autosave. The curation tool writes here when invoked.
      </>
    ),
  },
  {
    name: "Table",
    badge: "Wiki",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: "Structured data with typed columns (text, number, date, select, etc.). Filters, sorting, views, CSV import/export. Optional row embeddings for semantic search — configure which columns to embed.",
  },
  {
    name: "File",
    badge: "Attachment",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Images, PDFs, and documents stored in S3-compatible storage (Cloudflare R2, AWS S3, or MinIO). Uploadable as attachments via the API or notebook editor.",
  },
  {
    name: "Search",
    badge: "Cross-cutting",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Universal cross-resource AI search. Ask a natural language question and get a synthesized answer across notebooks, tables, history, and files. Supports workspace scoping and resource type filtering.",
  },
  {
    name: "Curation",
    badge: "Tool",
    badgeColor: "bg-amber-500/10 text-amber-600",
    desc: "Automated process that reads workspace data (history, notebooks, tables) and calls Claude to organize it into categorized wiki pages — merging duplicates, creating backlinks, and organizing folders. Runs automatically after agent sessions (with a 24-hour cooldown) or on demand via the /curate slash command in supported agents.",
  },
];

export default function ConceptsPage() {
  return (
    <>
      <Title>Concepts</Title>
      <Subtitle>Every resource in Stash, clearly defined.</Subtitle>

      <div className="space-y-3">
        {CONCEPTS.map((c) => (
          <div key={c.name} className="rounded-2xl border border-border bg-surface px-5 py-4">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-[15px] font-semibold text-foreground">{c.name}</span>
              <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${c.badgeColor}`}>
                {c.badge}
              </span>
            </div>
            <P>{c.desc}</P>
          </div>
        ))}
      </div>
    </>
  );
}
