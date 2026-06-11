import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../_components/SiteHeader";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export const metadata: Metadata = {
  title: "Agent-native Drive · Stash",
  description:
    "An agent-native Google Drive in Markdown and HTML. Real-time collaborative editing for you and your agents, reachable through the CLI, MCP, and API.",
};

const FEATURES = [
  [
    "Markdown & HTML, natively",
    "Pages are real Markdown and HTML — plus CSV, PDF, and images. The formats your agent already reads and writes, not a proprietary block format.",
  ],
  [
    "WYSIWYG HTML editing",
    "When your agent builds an HTML page — a report, a dashboard, a deck — you edit it visually in a WYSIWYG editor. Tweak the result by hand without touching the markup.",
  ],
  [
    "Real-time collaboration",
    "You and your agent edit the same page at the same time — two cursors at once. Edits save automatically.",
  ],
  [
    "A virtual filesystem",
    "The whole Drive mounts as a filesystem your agent can ls, find, and rg — pages, files, and session transcripts side by side.",
  ],
  [
    "Reachable everywhere",
    "Through the CLI, the Stash MCP server, or the HTTP API. Point Claude Code, Cursor, Codex, or OpenCode at it and they read and write directly.",
  ],
  [
    "Sessions land here too",
    "Every coding-agent session streams in automatically, indexed alongside your docs — no manual upload, no copy-paste.",
  ],
  [
    "Share a slice",
    "Bundle any set of pages into a Cartridge with a link, or share a folder with specific people — teammates and their agents work from the same docs.",
  ],
];

export default function AgentNativeDrivePage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="border-b border-border-subtle py-24 md:py-32">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Agent-native Drive
          </p>
          <h1 className="mt-5 max-w-[900px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-black leading-[1.02] tracking-[-0.04em] text-ink">
            A Google Drive your{" "}
            <span className="text-brand">agents can actually use.</span>
          </h1>
          <p className="mt-7 max-w-[620px] text-[18px] leading-[1.55] text-foreground">
            Write with your agent in real time on pages that are real Markdown and
            HTML — and when it builds an HTML page, edit the result visually in a
            WYSIWYG editor. The whole Drive — pages, files, and session
            transcripts — is reachable through the CLI, MCP, and API, so your
            agent reads and writes it as naturally as you do.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href={APP_URL}
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Start free →
            </Link>
            <Link
              href="/docs/quickstart"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Quickstart →
            </Link>
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Built for the way agents read and write.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(([name, blurb]) => (
              <div
                key={name}
                className="rounded-[12px] border border-border bg-background p-5 transition-colors hover:border-brand"
              >
                <div className="font-display text-[17px] font-bold tracking-[-0.01em] text-ink">
                  {name}
                </div>
                <p className="mt-1.5 text-[14px] leading-[1.55] text-dim">{blurb}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Sharing
          </p>
          <h2 className="mt-5 max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Sharing is built in, not bolted on.
          </h2>
          <p className="mt-5 max-w-[620px] text-[16px] leading-[1.6] text-foreground">
            Everything in your Drive is one step away from being shared — with a
            teammate, a client, or the public. The people you share with bring
            their own agents, and everyone works from the same source.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-8 md:grid-cols-3 md:gap-12">
            <Point title="Publish a Cartridge">
              Bundle any set of pages, files, and sessions into a Cartridge and
              share it as a link — public on Discover, or private to a few people.
            </Point>
            <Point title="Share a folder">
              Give specific people read or write access to a folder. Their agents
              get the same access, so context is shared, not copy-pasted.
            </Point>
            <Point title="Fork and stay in sync">
              Anyone can fork a published Cartridge into their own workspace, and
              it stays live with the source as it changes.
            </Point>
          </div>
        </div>
      </section>

      <section className="bg-surface py-28 text-center">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-black leading-[1.0] tracking-[-0.04em] text-ink">
            Give your agents somewhere to write.
          </h2>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href={APP_URL}
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Start free →
            </Link>
            <Link
              href="/connect-your-data"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Connect your data →
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}

function Point({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="font-display text-[19px] font-bold tracking-[-0.01em] text-ink">{title}</h3>
      <p className="mt-2.5 text-[15px] leading-[1.6] text-dim">{children}</p>
    </div>
  );
}
