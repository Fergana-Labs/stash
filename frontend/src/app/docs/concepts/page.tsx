import { Code, P, Title, Subtitle } from "../components";

export default function ConceptsPage() {
  return (
    <>
      <Title>Concepts</Title>
      <Subtitle>Everything in Boozle, explained.</Subtitle>

      <div className="space-y-6">
        {[
          { name: "Workspace", badge: "Container", desc: "Top-level permissioned container. Members share all resources. Invite others with a code. Set visibility to public or private." },
          { name: "Files", badge: "Consume", desc: "Upload images, PDFs, documents to S3 storage. Attach to chat messages, reference in notebook pages. Import bookmarks via CLI." },
          { name: "History", badge: "Consume", desc: "Append-only event logs from AI agents. Every tool call, message, and session event is recorded with timestamps, agent names, and metadata. Searchable via FTS and semantic search. The sleep agent reads history to curate the wiki." },
          { name: "Tables", badge: "Consume", desc: "Structured data with typed columns (text, number, date, select, etc.). Filters, sorting, views, CSV import/export. Optional row embeddings for semantic search." },
          { name: "Notebooks", badge: "Curate", desc: "Wiki-style markdown pages organized in folders. The sleep agent writes here — category pages, content summaries, pattern cards. [[Page Name]] wiki links with backlinks, page graph visualization, and semantic search. Real-time collaborative editing via Yjs." },
          { name: "Personas", badge: "Curate", desc: "Sleep agent + notebook. Each persona watches workspace history stores (optionally filtered by agent_name) and curates what it finds into its personal notebook wiki. Configure which workspaces, agent names, sources, interval, and model." },
          { name: "Chats", badge: "Collaborate", desc: "Real-time messaging channels within a workspace. Also personal rooms and DMs. File attachments. Agents participate alongside humans." },
          { name: "Pages", badge: "Collaborate", desc: "HTML/JS/CSS documents for shareable output — analytics reports, slide decks, dashboards. Agents generate these. Public sharing with token-based access, optional passcode/email gates, and viewer analytics." },
          { name: "Search", badge: "Cross-cutting", desc: "Universal cross-resource search powered by AI. Ask a question and get a synthesized answer across notebooks, tables, history, and documents. Supports workspace scoping and resource type filtering." },
        ].map((c) => (
          <div key={c.name} className="border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium text-foreground">{c.name}</span>
              <span className="text-[10px] text-muted font-mono bg-raised px-1.5 py-0.5 rounded">{c.badge}</span>
            </div>
            <P>{c.desc}</P>
          </div>
        ))}
      </div>
    </>
  );
}
