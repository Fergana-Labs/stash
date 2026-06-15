import type { Metadata } from "next";
import Link from "next/link";

import MarkdownView from "../_components/MarkdownView";
import { AGENT_DOCS } from "../_lib/agent-docs";

export const metadata: Metadata = {
  title: "Agent instructions · Stash Pages",
  description:
    "How agents create, read, and update Stash Pages over plain HTTP — same options and links as the UI.",
};

// Human-readable rendering of the agent manual. Agents fetching this
// URL with curl/web tools get the raw markdown via the proxy's content
// negotiation (served from ./raw).
export default function AgentDocsPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border-subtle">
        <div className="mx-auto flex max-w-[1100px] items-center gap-4 px-6 py-3">
          <Link href="/pages" className="font-mono text-[12px] text-muted hover:text-ink">
            ← stash pages
          </Link>
          <span className="text-[14.5px] font-medium text-ink">Agent instructions</span>
        </div>
      </header>
      <div className="mx-auto max-w-[1100px] px-6 py-2">
        <MarkdownView content={AGENT_DOCS} />
        <p className="mx-auto max-w-[920px] px-6 pb-10 text-[13px] text-muted">
          Tip: just give your agent this page&apos;s URL — fetching it returns these
          instructions as plain markdown.
        </p>
      </div>
    </main>
  );
}
