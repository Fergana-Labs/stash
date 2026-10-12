import Link from "next/link";

import AppRedirectForSignedInUsers from "./AppRedirectForSignedInUsers";
import GetStartedMenu from "./GetStartedMenu";
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

const WRITING = [
  {
    title: "State of the art on BEAM 10M",
    body: "Stash leads BEAM at every scale, by +4.6 points at 10M tokens where grep collapses, and answers a 1M-token corpus 46x cheaper than putting it in context.",
    date: "Oct 2026",
    href: "/blog/state-of-the-art-beam-10m",
  },
  {
    title: "Why memory is unsolved",
    body: "Memory is not retrieval. Perfect search is not enough; the problems actually holding memory back are blast radius and stability under accumulation.",
    date: "Sep 2026",
    href: "/blog/why-memory-is-unsolved",
  },
  {
    title: "Agent traces are the new oil",
    body: "The tokens agents produce will become the most valuable data in any organization: the decisions, context, and work output of teams, ready to train new models.",
    date: "Sep 2026",
    href: "/blog/agent-traces-are-the-new-oil",
  },
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <AppRedirectForSignedInUsers appUrl={APP_URL} />
      <Link
        href="/blog/state-of-the-art-beam-10m"
        className="block bg-brand px-5 py-2.5 text-center text-[14px] text-white transition hover:bg-brand-hover"
      >
        <span className="font-medium">New:</span> Stash sets state of the art on the BEAM 10M
        memory benchmark <span aria-hidden="true">→</span>
      </Link>
      <SiteHeader />

      <section className="mx-auto max-w-[1180px] px-5 pb-14 pt-24 sm:px-7 md:pb-20 md:pt-36">
        <h1 className="max-w-[18ch] font-display text-[clamp(38px,5vw,64px)] font-medium leading-[1.06] tracking-[-0.028em] text-ink">
          Agents that learn from the <span className="text-brand">real world.</span>
        </h1>
        <p className="mt-6 max-w-[58ch] text-[18px] leading-[1.6] text-dim">
          Stash is an applied AI lab building continual learning. We help you search, share, and
          learn from agent traces. Improve your agents automatically rather than relying on
          handcrafted evals or RL environments.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <GetStartedMenu appUrl={APP_URL} />
        </div>
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
              body="Coding agents that keep what they learn. Import the logs you already have and stop repeating yourself."
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
          <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-muted">Writing</p>
          <div className="mt-6">
            {WRITING.map(({ title, body, date, href }) => (
              <Link
                key={title}
                href={href}
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
