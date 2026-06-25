import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../_components/SiteHeader";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export const metadata: Metadata = {
  title: "Memory · Stash",
  description:
    "Best-in-class agent memory: a three-way hybrid index — curated wiki, vector search, and grep — so your agents retrieve the right thing every time. Every retrieval method has blind spots; Stash runs all three.",
};

const METHODS = [
  {
    name: "Curated wiki",
    tag: "structure",
    blurb:
      "While you sleep, an agent curates your history into linked pages — a virtual file system your agents navigate directly, the way a teammate would open the right doc.",
  },
  {
    name: "Vector search",
    tag: "meaning",
    blurb:
      "Every session, page, and table is embedded, so agents find knowledge by meaning — not by remembering the exact filename or wording.",
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
    body: "One memory the whole team and every agent reads from — no per-agent black box, no knowledge trapped in one run's context.",
  },
  {
    title: "Kept in sync",
    body: "As your connected sources change, the index updates — agents reason over the current state of your work, not a stale snapshot.",
  },
  {
    title: "Cited back to the source",
    body: "Retrieved knowledge links to where it came from — the page, session, or table — so answers are checkable, not vibes.",
  },
];

export default function MemoryPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="border-b border-border-subtle py-24 md:py-32">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Memory
          </p>
          <h1 className="mt-5 max-w-[900px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.04em] text-ink">
            Your team&apos;s memory,{" "}
            <span className="text-brand">actually retrievable.</span>
          </h1>
          <p className="mt-7 max-w-[640px] text-[18px] leading-[1.55] text-foreground">
            Every retrieval method has blind spots, so Stash runs three at once — a
            curated wiki, vector search, and grep. Your agents get the best of all
            worlds, instead of one index that misses.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
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

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Three indexes, one retrieval.
          </h2>
          <p className="mt-4 max-w-[620px] text-[17px] leading-[1.55] text-dim">
            A question runs against all three and the results merge — keyword
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

      <section className="bg-surface py-28 text-center">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-bold leading-[1.0] tracking-[-0.04em] text-ink">
            Memory your agents can actually find.
          </h2>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href={APP_URL}
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Start free →
            </Link>
            <Link
              href="/agent-drive"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              See the Agent Drive →
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
