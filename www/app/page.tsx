import Link from "next/link";

import CopyButton from "./_components/CopyButton";

const INSTALL_COMMAND = `bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"`;

export default function Page() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <Nav />
      <Hero />
      <Problem />
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
    <header className="sticky top-0 z-30 border-b border-border-subtle bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1120px] items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2 font-display text-[22px] font-bold tracking-tight text-brand">
          <Logo size={28} />
          stash
        </Link>
        <nav className="flex items-center gap-6 text-[14px] text-dim sm:gap-8">
          <Link href="https://github.com/Fergana-Labs/octopus" className="hidden items-center gap-1.5 hover:text-ink sm:inline-flex">
            GitHub
          </Link>
          <Link href="/docs" className="hover:text-ink">
            Docs
          </Link>
          <Link href="/login" className="hover:text-ink">
            Sign in
          </Link>
          <Link
            href="#install"
            className="inline-flex h-9 items-center rounded-md bg-brand px-4 font-medium text-white shadow-sm transition hover:bg-brand-hover"
          >
            Install
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  const prompt = `Set up stash in this repo so our Claude Code sessions share memory with the team. (1) Install or upgrade the CLI: \`stash signin --help >/dev/null 2>&1 || pipx install stashai --force 2>/dev/null || uv tool install stashai --force\`. (2) Add the Claude Code plugin: \`claude plugin marketplace add Fergana-Labs/stash\` then \`claude plugin install stash@stash-plugins\`. (3) Run \`stash signin\` to open the sign-in page in my browser, then ask me to paste the token back. Run \`stash auth https://api.stash.ac --api-key <token>\`. (4) Run \`stash workspaces list --mine --json\` — if I have multiple, ask which one and run \`stash workspaces use <id>\`. (5) Run \`stash connect --welcome\` and render its full output back to me as a markdown block in your reply, verbatim — don't summarize, don't add commentary, don't truncate. (Future sessions can re-read it via the \`/stash:welcome\` slash command, but you can't invoke that yourself.)`;
  return (
    <section id="install" className="relative overflow-hidden border-b border-border-subtle">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px] bg-[radial-gradient(ellipse_at_top,rgba(249,115,22,0.10),transparent_60%)]"
      />
      <div className="mx-auto max-w-[960px] px-6 pb-20 pt-16 text-center sm:pt-24">
        <Link
          href="https://github.com/Fergana-Labs/octopus"
          className="inline-flex items-center gap-3 rounded-full border border-border bg-surface/80 py-1.5 pl-1.5 pr-4 text-[12px] text-dim shadow-sm backdrop-blur transition hover:border-brand/40 hover:text-ink"
        >
          <span className="rounded-full bg-brand px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-white">
            New
          </span>
          <span>Plugin marketplace live for Claude Code</span>
          <span className="text-muted">→</span>
        </Link>

        <h1 className="mt-8 text-balance font-display text-[clamp(40px,5.6vw,72px)] font-black leading-[0.98] tracking-[-0.04em] text-ink">
          <span className="text-brand">Shared memory</span> for teams of AI coding agents.
        </h1>

        <p className="mx-auto mt-7 max-w-[640px] text-[18px] leading-[1.55] text-dim">
          When a teammate&apos;s coding agent fixes a bug, yours does too. Every
          session, decision, and search becomes part of one living knowledge
          base — queryable by every agent on the team.
        </p>

        <div className="mx-auto mt-12 max-w-[760px] text-left">
          <div className="overflow-hidden rounded-xl border border-border-subtle bg-inverted shadow-[0_30px_80px_-40px_rgba(15,23,42,0.45)]">
            <div className="flex items-center justify-between border-b border-white/5 px-4 py-2">
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                <span className="ml-3 font-mono text-[11px] uppercase tracking-[0.14em] text-on-inverted-dim">
                  install
                </span>
              </div>
              <CopyButton value={INSTALL_COMMAND} />
            </div>
            <div className="overflow-x-auto px-5 py-5 font-mono text-[13px] leading-[1.7] text-on-inverted sm:text-[14px]">
              <div className="flex gap-3">
                <span className="shrink-0 select-none text-brand">$</span>
                <span className="whitespace-nowrap">{INSTALL_COMMAND}</span>
              </div>
            </div>
          </div>
          <p className="mt-3 text-center text-[13px] leading-[1.5] text-dim">
            Installs the CLI, walks you through scope · sign-in · workspace ·
            agent plugin. Re-run safe.
          </p>
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 text-[14px]">
          <Link
            href="https://github.com/Fergana-Labs/octopus"
            className="inline-flex items-center font-medium text-ink hover:text-brand"
          >
            View on GitHub
            <span className="ml-2">→</span>
          </Link>
          <span className="text-muted">·</span>
          <Link
            href="/docs/quickstart"
            className="font-medium text-dim hover:text-brand"
          >
            Read the docs
          </Link>
        </div>

        <details className="group mx-auto mt-12 max-w-[760px] text-left">
          <summary className="cursor-pointer list-none text-center text-[13px] text-dim hover:text-brand">
            <span className="inline-block transition-transform group-open:rotate-90">
              ›
            </span>{" "}
            Or have your AI coding agent set it up
          </summary>
          <div className="mt-4 overflow-hidden rounded-xl border border-border-subtle bg-inverted shadow-[0_30px_80px_-40px_rgba(15,23,42,0.45)]">
            <div className="flex items-center justify-between border-b border-white/5 px-5 py-2.5">
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-on-inverted-dim">
                claude code
              </span>
              <span className="font-mono text-[11px] text-on-inverted-dim">
                prompt
              </span>
            </div>
            <div className="px-5 py-4 font-mono text-[13px] leading-[1.7] text-on-inverted">
              <div className="flex gap-3">
                <span className="shrink-0 text-brand">&gt;</span>
                <PromptBody text={prompt} />
              </div>
            </div>
          </div>
          <p className="mt-3 text-[13px] leading-[1.5] text-dim">
            Paste into Claude Code (or any other coding agent with shell
            access). Same end state as the one-liner.
          </p>
        </details>
      </div>
    </section>
  );
}

function PromptBody({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <p className="whitespace-pre-wrap break-words">
      {parts.map((part, i) =>
        part.startsWith("`") && part.endsWith("`") ? (
          <code key={i} className="rounded bg-white/10 px-1.5 py-0.5 text-on-inverted">
            {part.slice(1, -1)}
          </code>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
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
