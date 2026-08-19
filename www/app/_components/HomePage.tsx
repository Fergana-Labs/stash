import Link from "next/link";

import AppRedirectForSignedInUsers from "./AppRedirectForSignedInUsers";
import SiteFooter from "./SiteFooter";
import SiteHeader from "./SiteHeader";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

const BELIEFS = [
  [
    "AI will outproduce humans.",
    "Soon, agents will produce more work than the humans they work with. Jevon's paradox will come in full force.",
  ],
  [
    "Agent traces are the new oil.",
    "The tokens that agents produce will become the most valuable data in any organization. They contain the decisions, context, and work output of teams which can be used to train new models.",
  ],
  [
    "Personalized models beat general ones.",
    "No matter how smart frontier models become, they will not know your specific workflow or style. Personalized models with operational knowledge of your SOPs will outperform.",
  ],
  [
    "Modularity unlocks future scaling.",
    "The next frontier of scaling will be based on enabling models and agents to build on top of each other rather than handcrafting evals and pipelines.",
  ],
];

const RESEARCH = [
  [
    "Memory as a world model, not retrieval",
    "Pure search is not sufficient for good memory. We argue for the need to build “world models” where agents develop internal representations of their environment.",
    "Aug 2026",
  ],
  [
    "Blast radius",
    "Information can expire, be outdated, or only apply in specific situations. Humans are great at these judgement calls around scope but agents are currently lacking.",
    "Jul 2026",
  ],
  [
    "Stability under accumulation",
    "Memory stores degrade over time due to slop, context rot, and entropy. We measure this problem using a technique inspired by PCR.",
    "Jun 2026",
  ],
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <AppRedirectForSignedInUsers appUrl={APP_URL} />
      <SiteHeader />

      <section className="mx-auto grid max-w-[1180px] grid-cols-1 items-center gap-10 px-5 pb-14 pt-24 sm:px-7 md:pb-20 md:pt-36 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:gap-16">
        <div>
        <h1 className="max-w-[18ch] font-display text-[clamp(38px,5vw,64px)] font-medium leading-[1.06] tracking-[-0.028em] text-ink">
          Agents that learn from the <span className="text-brand">real world.</span>
        </h1>
        <p className="mt-6 max-w-[58ch] text-[18px] leading-[1.6] text-dim">
          Stash is an applied AI lab building continual learning. We help you search, share, and
          learn from agent traces. Improve your agents automatically rather than relying on
          handcrafted evals or RL environments.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/internal-agents"
            className="inline-flex h-[46px] items-center rounded-[10px] bg-brand px-5 text-[15px] font-medium text-white transition hover:bg-brand-hover"
          >
            For internal agents
          </Link>
          <Link
            href="/external-agents"
            className="inline-flex h-[46px] items-center rounded-[10px] border border-border px-5 text-[15px] font-medium text-ink transition hover:border-ink"
          >
            For external agents
          </Link>
        </div>
        </div>

        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/octopus.webp"
          width={900}
          height={811}
          alt="The Stash octopus"
          className="mx-auto w-full max-w-[380px] lg:max-w-[440px]"
        />
      </section>

      <section className="border-t border-border-subtle py-16 md:py-24">
        <div className="mx-auto max-w-[1180px] px-5 sm:px-7">
          <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-muted">
            What we believe
          </p>
          <ol className="mt-8">
            {BELIEFS.map(([claim, body], i) => (
              <li
                key={claim}
                className="grid grid-cols-[44px_minmax(0,1fr)] items-baseline gap-x-4 gap-y-1 border-t border-border-subtle py-[22px] last:border-b lg:grid-cols-[62px_minmax(0,1fr)_minmax(0,1.25fr)] lg:gap-x-11"
              >
                <span className="font-mono text-[12px] text-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h2 className="font-display text-[clamp(19px,2vw,23px)] font-medium tracking-[-0.028em] text-ink">
                  {claim}
                </h2>
                <p className="col-start-2 text-[15.5px] leading-[1.6] text-dim lg:col-start-3">
                  {body}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="border-t border-border-subtle py-16 md:py-24">
        <div className="mx-auto max-w-[1180px] px-5 sm:px-7">
          <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-muted">
            Where to start
          </p>
          <div className="mt-7 grid grid-cols-1 gap-4 md:grid-cols-2">
            <Door
              kicker="Internal agents"
              title="The agents your team runs"
              body="Coding agents that keep what they learn. One prompt imports the logs you already have."
              cta="See the product →"
              href="/internal-agents"
            />
            <Door
              kicker="External agents"
              title="The agents your customers use"
              body="Memory for production agents, documented end to end: capture, refine, recall, isolate."
              cta="For external agents →"
              href="/external-agents"
            />
          </div>
        </div>
      </section>

      <section className="border-t border-border-subtle py-16 md:py-24">
        <div className="mx-auto max-w-[1180px] px-5 sm:px-7">
          <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-muted">Research</p>
          <div className="mt-6">
            {RESEARCH.map(([title, body, date]) => (
              <Link
                key={title}
                href="/blog"
                className="group grid grid-cols-[minmax(0,1fr)_110px] items-baseline gap-5 border-t border-border-subtle py-5 last:border-b"
              >
                <span>
                  <span className="font-display text-[19px] font-medium tracking-[-0.02em] text-ink transition group-hover:text-brand">
                    {title}
                  </span>
                  <p className="mt-1.5 max-w-[62ch] text-[15px] leading-[1.6] text-dim">{body}</p>
                </span>
                <span className="text-right font-mono text-[11.5px] uppercase tracking-[0.08em] text-muted">
                  {date}
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <SiteFooter />
    </main>
  );
}

function Door({
  kicker,
  title,
  body,
  cta,
  href,
}: {
  kicker: string;
  title: string;
  body: string;
  cta: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="flex min-h-[210px] flex-col rounded-[14px] border border-border bg-white p-[26px] transition hover:border-brand"
    >
      <span className="font-mono text-[11.5px] uppercase tracking-[0.12em] text-muted">
        {kicker}
      </span>
      <span className="mt-3.5 font-display text-[24px] font-medium tracking-[-0.028em] text-ink">
        {title}
      </span>
      <p className="mt-2.5 text-[15.5px] leading-[1.6] text-dim">{body}</p>
      <span className="mt-auto pt-5 text-[14.5px] text-brand">{cta}</span>
    </Link>
  );
}
