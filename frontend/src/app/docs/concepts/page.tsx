import { Code, P, Title, Subtitle } from "../components";

const CONCEPTS: { name: string; badge: string; badgeColor: string; desc: React.ReactNode }[] = [
  {
    name: "Workspace",
    badge: "Container",
    badgeColor: "bg-blue-500/10 text-blue-500",
    desc: "Top-level permissioned container. Members share all resources — notebooks, chats, history stores, tables, files. Invite others with a short code. Set visibility to public or private.",
  },
  {
    name: "Persona",
    badge: "Memory",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: (
      <>
        <strong className="text-foreground">A persona is an agent&apos;s memory inside Octopus — not the agent itself.</strong>{" "}
        Three components work together: a <strong className="text-foreground">personal notebook</strong> where
        curated knowledge lives; a <strong className="text-foreground">sleep agent</strong> that reads workspace
        history stores on a schedule and writes organised wiki pages into that notebook; and an{" "}
        <strong className="text-foreground">injection engine</strong> that scores notebook pages and recent history
        events by relevance, recency, staleness, and confidence, then selects the best ones to prepend to the
        agent&apos;s context at each prompt.
        <br /><br />
        Personas deliberately own <em>no</em> behavioural config — no skills, no system prompts, no CLAUDE.md.
        Those belong to the agent framework. Octopus&apos;s scope is semantic memory only: what the agent knows,
        not how it acts.
      </>
    ),
  },
  {
    name: "History Store",
    badge: "Consume",
    badgeColor: "bg-brand/10 text-brand",
    desc: "Append-only event log. Every tool call, message, and session event is recorded with timestamps, agent names, and metadata. Searchable via full-text and semantic search. The sleep agent reads history to curate the wiki.",
  },
  {
    name: "Notebook",
    badge: "Curate",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: (
      <>
        Wiki-style markdown pages organised in folders. The sleep agent writes here — category pages,
        content summaries, pattern cards.{" "}
        <Code>{"[[Page Name]]"}</Code> wiki links with backlinks, page graph visualisation, and semantic
        search. Real-time collaborative editing via Yjs.
      </>
    ),
  },
  {
    name: "Table",
    badge: "Consume",
    badgeColor: "bg-brand/10 text-brand",
    desc: "Structured data with typed columns (text, number, date, select, etc.). Filters, sorting, views, CSV import/export. Optional row embeddings for semantic search — configure which columns to embed.",
  },
  {
    name: "File",
    badge: "Consume",
    badgeColor: "bg-brand/10 text-brand",
    desc: "Images, PDFs, and documents stored in S3-compatible storage (Cloudflare R2, AWS S3, or MinIO). Attach to chat messages, reference in notebook pages, import from browser bookmarks.",
  },
  {
    name: "Chat",
    badge: "Collaborate",
    badgeColor: "bg-violet-500/10 text-violet-600",
    desc: "Real-time messaging channel within a workspace. WebSocket-based. Agents participate as first-class members. Also supports personal rooms (single-user) and DMs between any two users.",
  },
  {
    name: "Page (Deck)",
    badge: "Collaborate",
    badgeColor: "bg-violet-500/10 text-violet-600",
    desc: "HTML/JS/CSS documents for shareable output — analytics reports, slide decks, dashboards. Agents generate these via MCP. Public sharing with token-based access, optional passcode or email gate, and viewer analytics.",
  },
  {
    name: "Search",
    badge: "Cross-cutting",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Universal cross-resource AI search. Ask a natural language question and get a synthesised answer across notebooks, tables, history, and documents. Supports workspace scoping and resource type filtering.",
  },
  {
    name: "Sleep Agent",
    badge: "Curate",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: "Background worker tied to a persona. Runs on a configurable schedule (default 30 min). Reads newly ingested data, calls Claude, and writes categorised wiki pages — merging duplicates, creating backlinks, organising folders.",
  },
  {
    name: "Injection Engine",
    badge: "Retrieval",
    badgeColor: "bg-amber-500/10 text-amber-600",
    desc: (
      <>
        Runs on every prompt via <Code>POST /personas/me/inject</Code>. Scores candidates from the
        persona&apos;s notebook (always-inject pages, FTS-matched pages, pattern cards) and personal
        history (vector-similar events, FTS-matched events) using four factors:{" "}
        <strong className="text-foreground">relevance × recency × staleness × confidence</strong>.
        Fills a configurable token budget with a greedy knapsack algorithm, then returns a ranked
        context block to prepend to the prompt. Pattern cards use outcome-based confidence scoring.
        Recency uses spaced-repetition intervals across sessions.
      </>
    ),
  },
];

export default function ConceptsPage() {
  return (
    <>
      <Title>Concepts</Title>
      <Subtitle>Every resource in Octopus, clearly defined — including what each one deliberately does not do.</Subtitle>

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
