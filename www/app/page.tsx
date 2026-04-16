import Link from "next/link";

export default function Page() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <Nav />
      <Hero />
      <Problem />
      <Install />
      <HowItWorks />
      <Features />
      <Footer />
    </main>
  );
}

function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 72"
      width={size}
      height={(size * 72) / 64}
      aria-hidden="true"
    >
      <ellipse cx="32" cy="24" rx="22" ry="18" fill="#F97316" />
      <circle cx="25" cy="22" r="4" fill="#fff" />
      <circle cx="39" cy="22" r="4" fill="#fff" />
      <circle cx="26" cy="22" r="2" fill="#0F172A" />
      <circle cx="40" cy="22" r="2" fill="#0F172A" />
      <path d="M12 38 Q8 52 4 60" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M20 40 Q18 54 14 62" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M32 42 Q32 56 32 64" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M44 40 Q46 54 50 62" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M52 38 Q56 52 60 60" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
    </svg>
  );
}

function Nav() {
  return (
    <header className="border-b border-border-subtle">
      <div className="mx-auto flex h-16 max-w-[1120px] items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2 font-display text-[22px] font-bold tracking-tight text-brand">
          <Logo size={28} />
          stash
        </Link>
        <nav className="flex items-center gap-8 text-[14px] text-dim">
          <Link href="https://github.com/Fergana-Labs/octopus" className="hover:text-ink">
            GitHub
          </Link>
          <Link href="/docs" className="hover:text-ink">
            Docs
          </Link>
          <Link
            href="#install"
            className="inline-flex h-9 items-center rounded-md bg-brand px-4 font-medium text-white hover:bg-brand-hover"
          >
            Install
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="border-b border-border-subtle">
      <div className="mx-auto max-w-[1120px] px-6 pb-24 pt-32">
        <p className="mb-8 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          Open source · self-hostable · MIT
        </p>
        <h1 className="font-display text-[clamp(48px,6vw,88px)] font-black leading-[1.0] tracking-[-0.04em] text-ink">
          <span className="text-brand">Shared memory</span> for teams
          <br />
          of AI coding agents.
        </h1>
        <p className="mt-8 max-w-[640px] text-[21px] leading-[1.45] text-dim">
          When a teammate&apos;s coding agent fixes a bug, yours does too. Every
          session, decision, and search becomes part of one living knowledge
          base, queryable by every agent on the team.
        </p>
        <div className="mt-10 flex flex-wrap items-center gap-5">
          <Link
            href="#install"
            className="inline-flex h-12 items-center rounded-md bg-brand px-6 text-[15px] font-medium text-white hover:bg-brand-hover"
          >
            Install Stash
          </Link>
          <Link
            href="https://github.com/Fergana-Labs/octopus"
            className="inline-flex h-12 items-center px-2 text-[15px] font-medium text-ink hover:text-brand"
          >
            View on GitHub
            <span className="ml-2">→</span>
          </Link>
        </div>
      </div>
    </section>
  );
}

function Problem() {
  return (
    <section className="border-b border-border-subtle bg-surface">
      <div className="mx-auto max-w-[1120px] px-6 py-24">
        <p className="mb-6 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          The problem
        </p>
        <h2 className="max-w-[880px] font-display text-[40px] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          Every coding agent on your team starts from zero.
        </h2>
        <div className="mt-10 grid gap-10 text-[16px] leading-[1.65] text-foreground md:grid-cols-2">
          <p>
            Your agent just debugged a flaky auth test. An hour later your
            teammate&apos;s agent hits the same test and starts from scratch.
            Nobody told it what you learned.
          </p>
          <p>
            Multiply that across a week of work and half the team is
            reinventing the same fixes, rediscovering the same gotchas, and
            asking each other&apos;s humans for context their agents could
            have read themselves.
          </p>
        </div>
        <div className="mt-14 border-l-2 border-brand pl-6">
          <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
            Questions your agent can now ask
          </p>
          <ul className="space-y-3 font-display text-[22px] font-medium leading-[1.35] text-ink">
            <li>&ldquo;Why did Sam bump the rate limit from 100 to 500?&rdquo;</li>
            <li>&ldquo;Has anyone already tried fixing the memory leak in the backend?&rdquo;</li>
            <li>&ldquo;Is anyone else currently working on the API gateway?&rdquo;</li>
          </ul>
        </div>
      </div>
    </section>
  );
}

function Install() {
  const lines = [
    "pip install stash",
    "stash connect",
    "claude plugin install stash",
    "stash connect --welcome",
  ];
  return (
    <section id="install" className="border-b border-border-subtle">
      <div className="mx-auto max-w-[1120px] px-6 py-24">
        <p className="mb-6 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          Install
        </p>
        <h2 className="max-w-[760px] font-display text-[40px] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          One prompt. Your agent does the rest.
        </h2>
        <p className="mt-6 max-w-[680px] text-[17px] leading-[1.6] text-dim">
          Paste these into Claude Code (or run them yourself). The second step
          opens a browser to sign in; the others are non-interactive.
        </p>

        <div className="mt-12 overflow-hidden rounded-xl bg-inverted shadow-[0_24px_60px_-30px_rgba(15,23,42,0.4)]">
          <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-on-inverted-dim">
              terminal
            </span>
            <span className="font-mono text-[11px] text-on-inverted-dim">~</span>
          </div>
          <pre className="overflow-x-auto px-6 py-6 font-mono text-[14px] leading-[2] text-on-inverted">
            {lines.map((cmd) => (
              <div key={cmd}>
                <span className="mr-3 text-brand">$</span>
                <span>{cmd}</span>
              </div>
            ))}
          </pre>
        </div>

        <p className="mt-8 max-w-[680px] text-[14px] leading-[1.6] text-dim">
          After <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[13px] text-ink">stash connect</code>,
          a browser tab opens at stash.ac for sign-in. Everything after that
          runs without a prompt. When you&apos;re done, <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[13px] text-ink">stash connect --welcome</code>{" "}
          prints a rundown of what your agent can now do.
        </p>
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    {
      n: "01",
      label: "Stream",
      title: "Every session flows into a shared store.",
      body: "Prompts, tool calls, and session summaries push to your workspace's history as they happen. Nothing to remember to save.",
    },
    {
      n: "02",
      label: "Curate",
      title: "A curation agent turns noise into a wiki.",
      body: "On SessionEnd, stash:sleep reads recent history and organizes it into notebooks with [[backlinks]] and a page graph. Sleep-time compute, not session time.",
    },
    {
      n: "03",
      label: "Search",
      title: "Every agent queries the whole team's work.",
      body: "stash:search runs a cross-resource agentic loop over files, history, notebooks, tables, and chats. Your agent answers with sources, not hallucinations.",
    },
  ];
  return (
    <section className="border-b border-border-subtle bg-surface">
      <div className="mx-auto max-w-[1120px] px-6 py-24">
        <p className="mb-6 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          How it works
        </p>
        <h2 className="max-w-[760px] font-display text-[40px] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          Stream. Curate. Search. Nobody starts from zero.
        </h2>

        <div className="mt-16 divide-y divide-border-subtle border-y border-border-subtle">
          {steps.map((s) => (
            <div key={s.n} className="grid gap-6 py-10 md:grid-cols-[120px_1fr] md:gap-16">
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
                  {s.label}
                </p>
                <p className="mt-2 font-display text-[64px] font-black leading-none tracking-[-0.04em] text-ink/40">
                  {s.n}
                </p>
              </div>
              <div>
                <h3 className="font-display text-[24px] font-bold leading-[1.25] tracking-[-0.01em] text-ink">
                  {s.title}
                </h3>
                <p className="mt-3 max-w-[640px] text-[16px] leading-[1.65] text-foreground">
                  {s.body}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Features() {
  const items = [
    {
      title: "Shared history",
      body: "Every prompt and tool call streams to a team-wide event log. Searchable, filterable, attributable.",
    },
    {
      title: "Wiki notebooks",
      body: "Rich collaborative pages with [[backlinks]], page graph, and pgvector semantic search.",
    },
    {
      title: "Agentic search",
      body: "stash:search runs a cross-resource loop over every surface in the workspace. One query, every source.",
    },
    {
      title: "Real-time channels",
      body: "Agents and humans chat side-by-side in workspace channels. Coordinate, hand off, unblock.",
    },
    {
      title: "Shareable pages",
      body: "Publish research, reports, and dashboards as HTML anyone with a link can view.",
    },
    {
      title: "Self-hostable",
      body: "MIT license. Postgres + pgvector + FastAPI. Run it on your infra, keep your team's data yours.",
    },
  ];
  return (
    <section className="border-b border-border-subtle">
      <div className="mx-auto max-w-[1120px] px-6 py-24">
        <p className="mb-6 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          Features
        </p>
        <h2 className="max-w-[760px] font-display text-[40px] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          Everything one agent should know, every agent does.
        </h2>
        <div className="mt-14 grid gap-10 md:grid-cols-2 lg:grid-cols-3">
          {items.map((f) => (
            <div key={f.title}>
              <h3 className="font-display text-[20px] font-bold tracking-[-0.01em] text-ink">
                {f.title}
              </h3>
              <p className="mt-2 text-[15px] leading-[1.6] text-dim">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer>
      <div className="mx-auto flex max-w-[1120px] flex-col gap-8 px-6 py-16 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="flex items-center gap-2 font-display text-[28px] font-bold tracking-tight text-brand">
            <Logo size={34} />
            stash
          </p>
          <p className="mt-2 max-w-[360px] text-[14px] leading-[1.6] text-dim">
            Shared memory for teams of AI coding agents. Open source, MIT
            licensed, self-hostable.
          </p>
        </div>
        <div className="flex flex-wrap gap-8 text-[14px] text-dim">
          <Link href="https://github.com/Fergana-Labs/octopus" className="hover:text-ink">
            GitHub
          </Link>
          <Link href="/docs" className="hover:text-ink">
            Docs
          </Link>
          <Link href="/docs/quickstart" className="hover:text-ink">
            Quickstart
          </Link>
          <Link href="https://stash.ac" className="hover:text-ink">
            stash.ac
          </Link>
        </div>
      </div>
      <div className="border-t border-border-subtle">
        <div className="mx-auto max-w-[1120px] px-6 py-5">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
            © {new Date().getFullYear()} Fergana Labs · MIT
          </p>
        </div>
      </div>
    </footer>
  );
}
