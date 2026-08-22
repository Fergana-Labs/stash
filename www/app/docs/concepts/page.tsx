import type { Metadata } from "next";

import { Code, P, Title, Subtitle } from "../components";

const CONCEPTS: { name: string; badge: string; badgeColor: string; desc: React.ReactNode }[] = [
  {
    name: "Your Stash",
    badge: "Your space",
    badgeColor: "bg-blue-500/10 text-blue-500",
    desc: "Your personal scope. Everything you own lives here — pages, sessions, tables, and files — and your agent sees exactly what you can see: what you own, what's been shared with you, and what's public.",
  },
  {
    name: "Sessions",
    badge: "Events",
    badgeColor: "bg-brand/10 text-brand",
    desc: "The raw material. Every conversation your agents have — messages, tool calls, timestamps — streamed in by the plugin or pushed through the API, grouped into sessions, and searchable.",
  },
  {
    name: "Memory",
    badge: "Wiki",
    badgeColor: "bg-purple-500/10 text-purple-500",
    desc: "The refined layer: a wiki of linked pages compiled from your sessions, which your agents read before they work. Every page is an ordinary file you can open and edit — the curator treats your edits as source material.",
  },
  {
    name: "Curator",
    badge: "Agent",
    badgeColor: "bg-amber-500/10 text-amber-600",
    desc: "The agent that maintains the Memory wiki. It runs nightly (and on demand), reads only the sessions uploaded since its last run, and updates the wiki in place — cost scales with new conversation, not with how much you've stored.",
  },
  {
    name: "End user",
    badge: "Developer Platform",
    badgeColor: "bg-blue-500/10 text-blue-500",
    desc: "A user of your product, identified by your own user id. On the Developer Platform, each end user gets a private wiki the curator maintains for them, and opted-in users also feed one shared, anonymized wiki that every user's agent reads.",
  },
  {
    name: "Files",
    badge: "Files",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: (
      <>
        Markdown and HTML pages organized in folders. Rich-text editor with
        autosave, semantic search, and file attachments.
      </>
    ),
  },
  {
    name: "Table",
    badge: "Files",
    badgeColor: "bg-green-500/10 text-green-600",
    desc: "Structured data with typed columns (text, number, date, select, etc.). Filters, sorting, views, CSV import/export. Optional row embeddings for semantic search — configure which columns to embed.",
  },
  {
    name: "File",
    badge: "Attachment",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Images, PDFs, and documents stored in S3-compatible storage (Cloudflare R2, AWS S3, or MinIO). Uploadable as attachments via the API or files editor.",
  },
  {
    name: "Source",
    badge: "Virtual FS",
    badgeColor: "bg-amber-500/10 text-amber-600",
    desc: (
      <>
        Anything an agent can read, exposed as a virtual file system. Two native sources —{" "}
        <Code>files</Code> and <Code>sessions</Code> — are always present; connected sources
        (GitHub, Google Drive, Gmail, Notion, Slack, Granola) are added by you and indexed on a
        schedule. Pick a source like a drive, browse it by path, read a document, or search one
        source — or everything at once.
      </>
    ),
  },
  {
    name: "Skill",
    badge: "Bundle",
    badgeColor: "bg-purple-500/10 text-purple-500",
    desc: "A shareable bundle of pages, sessions, tables, and files — the unit you publish to a public link, list in Discover, or share with specific people.",
  },
  {
    name: "Sharing",
    badge: "Access",
    badgeColor: "bg-rose-500/10 text-rose-500",
    desc: "Resources are private by default. Grant a person access to a single folder, page, file, session, or table by email — pending invites convert automatically when they sign up — or convert a folder into a Skill to share everything in it together.",
  },
  {
    name: "Search",
    badge: "Cross-cutting",
    badgeColor: "bg-muted/20 text-muted",
    desc: "Unified search across every source. Scope to one source or search everything — native files and sessions plus your connected sources — in a single query.",
  },
];

export const metadata: Metadata = {
  title: "Concepts · Stash Docs",
  description:
    "Every resource in Stash clearly defined — files, sessions, skills, tables, sources, and the virtual filesystem your agents read.",
  alternates: { canonical: "/docs/concepts" },
};

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
