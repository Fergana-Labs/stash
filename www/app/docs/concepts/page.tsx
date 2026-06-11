import { Code, P, Title, Subtitle } from "../components";

const CONCEPTS: { name: string; badge: string; badgeColor: string; desc: React.ReactNode }[] = [
  {
    name: "Workspace",
    badge: "Container",
    badgeColor: "bg-blue-500/10 text-blue-500",
    desc: "Top-level permissioned container. Members share workspace resources: pages, sessions, tables, and files. Invite others with a short code.",
  },
  {
    name: "Sessions",
    badge: "Events",
    badgeColor: "bg-brand/10 text-brand",
    desc: "Append-only event log scoped to a workspace. Every tool call, message, and session event is recorded with timestamps, agent names, and metadata. Events are grouped by agent_name and session_id for a conversation-like view. Searchable via full-text search.",
  },
  {
    name: "Drive",
    badge: "Drive",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: (
      <>
        Folders, editable Markdown and HTML pages, uploaded files, and tables, scoped to a
        workspace. Agents can browse and edit it through the CLI and MCP.
      </>
    ),
  },
  {
    name: "Table",
    badge: "Drive",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: "Structured data with typed columns (text, number, date, select, etc.). Filters, sorting, views, CSV import/export. Optional row embeddings for semantic search — configure which columns to embed.",
  },
  {
    name: "File",
    badge: "Attachment",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Images, PDFs, and documents stored in S3-compatible storage (Cloudflare R2, AWS S3, or MinIO). Uploadable as attachments via the API or Drive editor.",
  },
  {
    name: "Source",
    badge: "Virtual FS",
    badgeColor: "bg-amber-500/10 text-amber-600",
    desc: (
      <>
        Anything an agent can read, exposed as a virtual file system. Two native sources —{" "}
        <Code>files</Code> and <Code>sessions</Code> — are always present; connected sources
        (GitHub, Google Drive, Gmail, Notion, Slack, Granola) are added per member and indexed on a
        schedule. Pick a source like a drive, browse it by path, read a document, or search one
        source — or everything at once.
      </>
    ),
  },
  {
    name: "Skill",
    badge: "Bundle",
    badgeColor: "bg-purple-500/10 text-purple-500",
    desc: "A shareable bundle of pages, sessions, tables, and files — the unit you publish to a public link, list in Discover, or share with specific people. Formerly called a Stash; the resource was renamed but the CLI name is unchanged.",
  },
  {
    name: "Sharing",
    badge: "Access",
    badgeColor: "bg-rose-500/10 text-rose-500",
    desc: "Resources are private by default. Grant a person access to a single folder, page, file, session, or table by email — pending invites convert automatically when they sign up — or bundle items into a Skill to share them together.",
  },
  {
    name: "Search",
    badge: "Cross-cutting",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Unified search across every source. Scope to one source or search everything — native files and sessions plus your connected sources — in a single query.",
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
