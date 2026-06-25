import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../_components/SiteHeader";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export const metadata: Metadata = {
  title: "Token Monitoring · Stash",
  description:
    "Monitor your team's agent sessions like Granola or Gong — onboard faster, coach your team, see what's happening across every session, and build automations for continual improvement.",
};

const FEATURES = [
  [
    "Onboarding",
    "New teammates learn from real sessions, not stale docs. Search how others solved the same problem and ramp on your codebase and tools in days, not weeks.",
  ],
  [
    "Coaching for your team",
    "See how each person prompts, where they get stuck, and what good looks like. Turn your best sessions into shared playbooks the whole team can learn from.",
  ],
  [
    "Monitoring",
    "Every session streams in automatically and is indexed full-text. Spot failures, dead ends, and risky patterns across the team without asking anyone for a recap.",
  ],
  [
    "Automations & workflows",
    "Mine recurring patterns into reusable Skills, prompts, and automations — so the lessons from one session compound into continual improvement for everyone.",
  ],
];

export default function TokenMonitoringPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="border-b border-border-subtle py-24 md:py-32">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Token Monitoring
          </p>
          <h1 className="mt-5 max-w-[900px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.04em] text-ink">
            Monitor your team&apos;s{" "}
            <span className="text-brand">agent sessions.</span>
          </h1>
          <p className="mt-7 max-w-[620px] text-[18px] leading-[1.55] text-foreground">
            Like Granola or Gong for your coding agents. Every session your team
            runs streams into Stash automatically and is indexed full-text — so
            you can onboard faster, coach your team, monitor what&apos;s
            happening, and build automations for continual improvement.
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
            Turn every session into team knowledge.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2">
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
            How it works
          </p>
          <h2 className="mt-5 max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            No manual capture. Nothing to copy-paste.
          </h2>
          <p className="mt-5 max-w-[620px] text-[16px] leading-[1.6] text-foreground">
            Point Claude Code, Cursor, Codex, or OpenCode at Stash and every
            session lands automatically — transcripts, files, and the decisions
            along the way — searchable across your whole team.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-8 md:grid-cols-3 md:gap-12">
            <Point title="Sessions stream in">
              Each coding-agent session is uploaded as it happens and indexed
              alongside your docs — no manual recap, no lost context.
            </Point>
            <Point title="Search across the team">
              Full-text and semantic search over every session. Find how a
              problem was solved, who hit the same wall, and what worked.
            </Point>
            <Point title="Compound the lessons">
              Promote the best patterns into shared Skills and automations, so
              what one person learns improves how everyone works.
            </Point>
          </div>
        </div>
      </section>

      <section className="bg-surface py-28 text-center">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-bold leading-[1.0] tracking-[-0.04em] text-ink">
            See how your team really works with agents.
          </h2>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href={APP_URL}
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Start free →
            </Link>
            <Link
              href="/company-brain"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              See the Company Brain →
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
