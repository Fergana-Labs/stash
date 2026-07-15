import type { Metadata } from "next";
import Link from "next/link";

import CtaPair from "../_components/CtaPair";
import SiteHeader from "../_components/SiteHeader";
import Texture from "../_components/Texture";

export const metadata: Metadata = {
  title: "Memory & Observability · Stash",
  description:
    "Best-in-class agent memory — a three-way hybrid index of curated wiki, vector search, and grep — plus observability over every agent session your team runs: onboarding, coaching, monitoring, and automations.",
};

const OBSERVABILITY = [
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
    "Mine recurring patterns into reusable Skills, prompts, and automations, so the lessons from one session compound into improvement for everyone.",
  ],
];

const METHODS = [
  {
    name: "Curated wiki",
    tag: "structure",
    blurb:
      "While you sleep, an agent curates your history into linked pages: a virtual file system your agents navigate directly, the way a teammate opens the right doc.",
  },
  {
    name: "Vector search",
    tag: "meaning",
    blurb:
      "Every session, page, and table is embedded, so agents find knowledge by meaning, not by remembering the exact filename or wording.",
  },
  {
    name: "Grep",
    tag: "exactness",
    blurb:
      "Agents search your Stash like a repo, for the literal identifiers, error strings, and names that embeddings gloss over.",
  },
];

const POINTS = [
  {
    title: "Shared, not per-agent",
    body: "One memory the whole team and every agent reads from. No per-agent black box, no knowledge trapped in one run's context.",
  },
  {
    title: "Kept in sync",
    body: "As your connected sources change, the index updates, so agents reason over the current state of your work, not a stale snapshot.",
  },
  {
    title: "Cited back to the source",
    body: "Retrieved knowledge links to where it came from, the page, session, or table, so answers are checkable, not guesses.",
  },
];

export default function MemoryPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="relative overflow-hidden border-b border-border-subtle py-24 md:py-32">
        <Texture className="h-[560px]" fade="top" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 z-0 h-[520px]"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 18% 8%, rgba(249,115,22,0.10), transparent 60%)",
          }}
        />
        <div className="relative z-10 mx-auto max-w-[1200px] px-7">
          <p className="kicker rise-in mb-6">Memory</p>
          <h1 className="max-w-[920px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-ink">
            Your team&apos;s memory,{" "}
            <span className="text-brand">actually retrievable.</span>
          </h1>
          <p className="mt-7 max-w-[640px] text-[18px] leading-[1.55] text-foreground">
            Every index has blind spots, so Stash runs three at once: a curated
            wiki for structure, vector search for meaning, and grep for exact
            identifiers. One query hits all three, so your agents retrieve the
            right thing instead of the closest match.
          </p>
          <div className="mt-9">
            <CtaPair />
          </div>
          <Link
            href="/company-brain"
            className="mt-5 inline-flex font-mono text-[13px] text-dim transition hover:text-brand"
          >
            See the Company Brain →
          </Link>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Three indexes, one retrieval.
          </h2>
          <p className="mt-4 max-w-[620px] text-[17px] leading-[1.55] text-dim">
            A question runs against all three and the results merge: keyword
            precision, semantic recall, and a navigable structure, together.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-5 lg:grid-cols-3">
            {METHODS.map((m) => (
              <div
                key={m.name}
                className="rounded-[12px] border border-border bg-background p-6 transition-colors hover:border-brand"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-display text-[19px] font-bold tracking-[-0.01em] text-ink">
                    {m.name}
                  </div>
                  <span className="rounded border border-border bg-raised px-1.5 py-0.5 font-mono text-[10.5px] text-dim">
                    {m.tag}
                  </span>
                </div>
                <p className="mt-3 text-[14.5px] leading-[1.6] text-dim">{m.blurb}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-20 md:py-28">
        <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-8 px-7 md:grid-cols-3 md:gap-12">
          {POINTS.map((p) => (
            <div key={p.title}>
              <h3 className="font-display text-[19px] font-bold tracking-[-0.01em] text-ink">
                {p.title}
              </h3>
              <p className="mt-2.5 text-[15px] leading-[1.6] text-dim">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="kicker">Observability</p>
          <h2 className="mt-5 max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            See how your team really works with agents.
          </h2>
          <p className="mt-5 max-w-[620px] text-[16px] leading-[1.6] text-foreground">
            The same memory that answers your agents&apos; questions records how
            they work. Every session your team runs streams into Stash
            automatically and is indexed full-text — Granola or Gong, but for
            coding agents.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {OBSERVABILITY.map(([name, blurb]) => (
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

      <section className="relative overflow-hidden py-28 text-center">
        <Texture className="opacity-70" fade="center" />
        <div className="relative z-10 mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-bold leading-[1.0] tracking-[-0.035em] text-ink">
            Memory your agents can actually find.
          </h2>
          <div className="mt-8 flex justify-center">
            <CtaPair align="center" />
          </div>
          <Link
            href="/company-brain"
            className="mt-6 inline-flex font-mono text-[13px] text-dim transition hover:text-brand"
          >
            See the Company Brain →
          </Link>
        </div>
      </section>
    </main>
  );
}
