import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../_components/SiteHeader";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export const metadata: Metadata = {
  title: "Connect your data · Stash",
  description:
    "The one place your agents connect to all your data — GitHub, Drive, Gmail, Notion, Slack, and more. Read and search across everything from day one.",
};

const SOURCES = [
  ["GitHub", "Pick repos your agent can navigate like a filesystem."],
  ["Google Drive", "Index My Drive and read docs on demand."],
  ["Gmail", "Search messages and read email on demand."],
  ["Notion", "Pages and databases you share with Stash."],
  ["Slack", "Channel history, kept in sync."],
  ["Granola", "Meeting notes and transcripts."],
  ["Jira", "Search issues across a project."],
  ["Asana", "Navigate tasks from a project."],
  ["Gong", "Call transcripts, kept in sync."],
  ["Snowflake", "Run read-only SQL against your warehouse."],
];

export default function ConnectYourDataPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="border-b border-border-subtle py-24 md:py-32">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Connect your data
          </p>
          <h1 className="mt-5 max-w-[900px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-black leading-[1.02] tracking-[-0.04em] text-ink">
            One place your agents connect to{" "}
            <span className="text-brand">all your data.</span>
          </h1>
          <p className="mt-7 max-w-[620px] text-[18px] leading-[1.55] text-foreground">
            Connect GitHub, Drive, Gmail, Notion, Slack and more in a couple of
            clicks. Your agent reads and searches across everything you connect —
            grounded on your real work from day one instead of starting empty.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href={APP_URL}
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Start free →
            </Link>
            <Link
              href="/contact-sales"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Talk to us
            </Link>
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Connect once. Your agent reads it all.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {SOURCES.map(([name, blurb]) => (
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
        <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-8 px-7 md:grid-cols-3 md:gap-12">
          <Point title="OAuth in two clicks">
            Connect a source from settings — no tokens to paste, no scripts to
            run. Access stays scoped to what you grant.
          </Point>
          <Point title="Kept in sync">
            Stash keeps connected sources fresh, so your agent reasons over the
            current state of your data, not a one-time export.
          </Point>
          <Point title="Search and ask across everything">
            Ask one question and your agent answers across every source at once —
            grounded on your stuff, with citations back to where it came from.
          </Point>
        </div>
      </section>

      <section className="bg-surface py-28 text-center">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-black leading-[1.0] tracking-[-0.04em] text-ink">
            Give your agents everything you know.
          </h2>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href={APP_URL}
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Start free →
            </Link>
            <Link
              href="/agent-native-drive"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              See the agent-native Drive →
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
