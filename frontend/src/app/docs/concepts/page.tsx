import { P, Title, Subtitle } from "../components";

const CONCEPTS: { name: string; badge: string; badgeColor: string; desc: React.ReactNode }[] = [
  {
    name: "Workspace",
    badge: "Container",
    badgeColor: "bg-blue-500/10 text-blue-500",
    desc: "Top-level permissioned container. Members share sessions, pages, files, tables, and Stashes. Invite others with a short code.",
  },
  {
    name: "Stash",
    badge: "Bundle",
    badgeColor: "bg-brand/10 text-brand",
    desc: "A curated bundle of related workspace artifacts (pages, sessions, files, folders) with its own access control and an optional public slug. Use one when you want a single shareable URL — for a project writeup with its sources, a research thread with its files, a coding session with its outputs. Stashes can be private, workspace-visible, or public (listed in Discover). Forkable: a public Stash can be copied into another workspace.",
  },
  {
    name: "Session",
    badge: "Transcript",
    badgeColor: "bg-purple-500/10 text-purple-500",
    desc: "Append-only event log scoped to a workspace. Every tool call, message, and agent event is recorded with timestamps, agent name, and metadata. Sessions are grouped by day and user for a conversation-like reader, and are searchable via full-text + semantic search.",
  },
  {
    name: "Files",
    badge: "Filesystem",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: (
      <>
        The workspace&apos;s virtual filesystem — nested folders containing
        pages (markdown / HTML documents with autosave + live collaboration)
        and uploads (images, PDFs, docs in S3-compatible storage). Everything
        lives in one tree: <code className="font-mono text-[13px]">stash files tree</code>,{" "}
        <code className="font-mono text-[13px]">stash vfs ls /</code>, and the
        sidebar all see the same nodes. Pages, folders, and uploads are kinds
        of files — not separate concepts.
      </>
    ),
  },
  {
    name: "Table",
    badge: "Structured data",
    badgeColor: "bg-amber-500/10 text-amber-600",
    desc: "Tables with typed columns (text, number, date, select, etc.). Filters, sorting, saved layouts, CSV import/export. Optional row embeddings for semantic search — configure which columns to embed.",
  },
  {
    name: "Discover",
    badge: "Cross-cutting",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Public catalog of Stashes opted into discoverability. Sortable by trending, newest, or popular. Stashes here can be forked into your own workspace.",
  },
  {
    name: "Activity",
    badge: "Cross-cutting",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Timeline of recent events across workspaces — session uploads, page edits, file uploads, Stash publishes. Filterable per-workspace or global.",
  },
  {
    name: "Search",
    badge: "Cross-cutting",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Cross-resource search over pages, tables, sessions, files, and Stashes. Supports workspace, Stash, folder, page, and internal-only scoping.",
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
