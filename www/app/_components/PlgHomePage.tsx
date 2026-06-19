import Link from "next/link";

import AppRedirectForSignedInUsers from "./AppRedirectForSignedInUsers";
import { ClosingCTA, Footer, Logos } from "./HomePage";
import LiveDemo from "./LiveDemo";
import SiteHeader from "./SiteHeader";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export default function PlgHomePage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <AppRedirectForSignedInUsers appUrl={APP_URL} />
      <SiteHeader />
      <Hero />
      <Logos />
      <UseCases />
      <ClosingCTA />
      <Footer />
    </main>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 z-0 h-[680px]"
        style={{
          background:
            "radial-gradient(ellipse 70% 55% at 50% 0%, rgba(249,115,22,0.10), transparent 60%)",
        }}
      />
      <div className="relative z-10 mx-auto flex max-w-[820px] flex-col items-center px-7 pb-16 pt-20 text-center lg:pt-28">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          A workspace for your agents
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(40px,6vw,72px)] font-black leading-[0.98] tracking-[-0.045em] text-ink">
          What should your agent
          <br />
          <span className="text-brand">make today?</span>
        </h1>
        <p className="mt-6 max-w-[600px] text-[18px] leading-[1.55] text-foreground">
          Bring your own agent and give it somewhere to work. Stash turns it
          into decks, dashboards, docs, and spreadsheets you can share — backed
          by a memory that compounds every time you use it.
        </p>

        <div className="mt-9 flex w-full justify-center text-left">
          <LiveDemo />
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link
            href={APP_URL}
            className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
          >
            Start free →
          </Link>
          <Link
            href="/teams"
            className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
          >
            For teams →
          </Link>
        </div>
      </div>
    </section>
  );
}

type UseCase = { tag: string; title: string; body: string };

// The grid doubles as a menu of Skills: each card is a repeatable process an
// agent can run, fork, and rerun. Grouped by the kind of work, Manus-style.
const USE_CASES: UseCase[] = [
  { tag: "Make", title: "Slides & decks", body: "Turn rough notes or a dataset into a polished, shareable deck." },
  { tag: "Make", title: "Analytics dashboards", body: "Build a live dashboard from raw data and publish it as a link." },
  { tag: "Make", title: "Spreadsheets", body: "Generate spreadsheets and watch how the data flows in, step by step." },
  { tag: "Make", title: "Docs you can publish", body: "Write docs and dashboards, then share any slice as a public URL." },
  { tag: "Make", title: "Write like you", body: "AI writing tuned to your voice, from your past work." },
  { tag: "Make", title: "Content library", body: "A marketing content library your agents draw from and add to." },
  { tag: "Make", title: "Creative generation", body: "Generate on-brand AI images and video for a campaign." },
  { tag: "Research", title: "Deep research", body: "Multi-source, fact-checked research on any topic, with citations." },
  { tag: "Research", title: "Research → spreadsheet", body: "Research anything and deliver it as a structured spreadsheet." },
  { tag: "Research", title: "Monitor a topic", body: "Track a topic, feed, or competitor over the last 30 days." },
  { tag: "Research", title: "Bookmark store", body: "Save podcasts, tweets, YouTube, and papers into one searchable store." },
  { tag: "Outreach", title: "Find people", body: "Research the right people and draft outreach that lands." },
  { tag: "Operate", title: "Lightweight CRM", body: "A CRM your agent keeps current from your email and calls." },
  { tag: "Operate", title: "Email & scheduling", body: "Triage your inbox and manage your calendar on your behalf." },
  { tag: "Operate", title: "Chase it down", body: "Follow up with people until the thing actually gets done." },
  { tag: "Operate", title: "Audit your agents", body: "Review what your agents did, then coach them to do it better." },
];

function UseCases() {
  return (
    <section className="border-b border-border-subtle py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="flex max-w-[760px] flex-col gap-4">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Use cases
          </p>
          <h2 className="font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
            A starting point for anything
            <br />
            <span className="font-medium text-dim">your agent can do.</span>
          </h2>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {USE_CASES.map((u) => (
            <div
              key={u.title}
              className="flex flex-col rounded-[12px] border border-border bg-background p-5 transition-colors hover:border-brand"
            >
              <span
                className="mb-3 inline-flex w-fit rounded px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-brand"
                style={{ background: "var(--brand-soft)" }}
              >
                {u.tag}
              </span>
              <h3 className="font-display text-[16.5px] font-bold tracking-[-0.01em] text-ink">
                {u.title}
              </h3>
              <p className="mt-2 text-[13.5px] leading-[1.55] text-dim">{u.body}</p>
            </div>
          ))}
        </div>

        <p className="mt-10 max-w-[680px] text-[15px] leading-[1.6] text-dim">
          Each one can become a{" "}
          <Link href="/skills" className="font-medium text-brand hover:underline">
            Skill
          </Link>
          {" "}— a folder your agents rerun, share with a link, and fork. The more
          you use it, the more your workspace knows.
        </p>
      </div>
    </section>
  );
}
