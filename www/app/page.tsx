import Link from "next/link";
import type { ReactNode } from "react";

import CopyButton from "./_components/CopyButton";
import ScrollLink from "./_components/ScrollLink";

const INSTALL_COMMAND = `bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"`;

export default function Page() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <Nav />
      <Hero />
      <Logos />
      <InstallSlab />
      <Problem />
      <HowItWorks />
      <SearchDemo />
      <Features />
      <ClosingCTA />
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

function EyebrowDot({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
      <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
      {children}
    </p>
  );
}

function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-border-subtle bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-7 sm:px-7">
        <Link
          href="/"
          className="flex items-center gap-2.5 font-display text-[20px] font-black tracking-[-0.03em] text-ink"
        >
          <Logo size={28} />
          stash
        </Link>
        <nav className="flex items-center gap-2 text-[14px] text-dim">
          <ScrollLink
            to="#how"
            className="hidden rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink sm:inline-flex"
          >
            How it works
          </ScrollLink>
          <ScrollLink
            to="#features"
            className="hidden rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink sm:inline-flex"
          >
            Features
          </ScrollLink>
          <Link
            href="/docs"
            className="rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink"
          >
            Docs
          </Link>
          <Link
            href="/login"
            className="hidden h-10 items-center rounded-lg border border-border bg-background px-[18px] text-[14px] font-medium text-ink transition hover:border-ink sm:inline-flex"
          >
            Sign in
          </Link>
          <ScrollLink
            to="#install"
            className="inline-flex h-10 items-center rounded-lg bg-brand px-[18px] text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
          >
            Install
          </ScrollLink>
        </nav>
      </div>
    </header>
  );
}

type FeedRow = {
  role: "agent" | "human";
  name: string;
  action: string;
  target: string;
  detail: ReactNode;
  time: string;
};

const HERO_FEED: FeedRow[] = [
  {
    role: "agent",
    name: "rex",
    action: "updated",
    target: "auth/session_refresh.py",
    detail: (
      <>
        fixed 401 race on concurrent refresh, linked to{" "}
        <span className="font-mono text-[11.5px] text-brand">[[auth-patterns]]</span>
      </>
    ),
    time: "just now",
  },
  {
    role: "human",
    name: "sam",
    action: "opened",
    target: "backend/gateway/",
    detail: "reviewing rate-limit bump from the rex debug session",
    time: "2m",
  },
  {
    role: "agent",
    name: "scout",
    action: "queried",
    target: "stash search",
    detail: (
      <>
        &ldquo;why was the{" "}
        <span className="font-mono text-[11.5px] text-brand">[[rate-limit]]</span> raised to 500?&rdquo; · 8 sources
      </>
    ),
    time: "4m",
  },
  {
    role: "agent",
    name: "nova",
    action: "curated",
    target: "wiki · memory-leak-v2",
    detail: "4 pages merged, 12 backlinks resolved on stash:sleep",
    time: "9m",
  },
  {
    role: "human",
    name: "ari",
    action: "commented",
    target: "notebooks/api-gateway",
    detail: "keeping this open; will re-use the worker-pool pattern next week",
    time: "22m",
  },
];

function Avatar({
  role,
  children,
  size = 24,
}: {
  role: "agent" | "human";
  children: ReactNode;
  size?: number;
}) {
  const bg = role === "agent" ? "var(--agent)" : "var(--human)";
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-display font-bold text-white"
      style={{ width: size, height: size, fontSize: size * 0.42, background: bg }}
    >
      {children}
    </span>
  );
}

function RoleTag({ role }: { role: "agent" | "human" }) {
  const style =
    role === "agent"
      ? { background: "var(--agent-soft)", color: "var(--agent)" }
      : { background: "var(--human-soft)", color: "var(--human)" };
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase leading-none tracking-[0.1em]"
      style={style}
    >
      {role}
    </span>
  );
}

function HeroFeed() {
  return (
    <div className="relative">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-[-20px] bottom-[-20px] -z-10 h-10"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(15,23,42,0.08), transparent 70%)",
        }}
      />
      <div
        className="overflow-hidden rounded-[14px] border border-border bg-background"
        style={{ boxShadow: "var(--shadow-card)" }}
      >
        <div className="flex items-center justify-between border-b border-border-subtle bg-surface px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span
              className="h-2 w-2 rounded-full bg-[#22C55E]"
              style={{ animation: "live-pulse 2s ease-out infinite" }}
            />
            <span className="text-[13px] font-semibold text-ink">team · fergana</span>
            <span className="text-[12px] text-muted">/ history</span>
          </div>
          <span className="inline-flex items-center gap-2 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-dim">
            Live
          </span>
        </div>
        <div className="max-h-[420px] overflow-hidden py-1.5">
          {HERO_FEED.map((r, i) => (
            <div
              key={i}
              className="grid grid-cols-[24px_1fr_auto] items-start gap-3 border-b border-border-subtle px-4 py-3 transition-colors last:border-b-0 hover:bg-surface"
            >
              <Avatar role={r.role} size={24}>
                {r.name[0].toUpperCase()}
              </Avatar>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="font-semibold text-ink">{r.name}</span>
                  <RoleTag role={r.role} />
                  <span className="text-dim">{r.action}</span>
                  <span className="rounded bg-raised px-1.5 py-px font-mono text-[12px] text-ink">
                    {r.target}
                  </span>
                </div>
                <div className="mt-1 text-[12.5px] leading-[1.55] text-dim">{r.detail}</div>
              </div>
              <span className="whitespace-nowrap pt-0.5 font-mono text-[10.5px] tracking-[0.06em] text-muted">
                {r.time}
              </span>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between border-t border-border-subtle bg-surface px-4 py-2.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted">
          <span>streaming · 412 events / hr</span>
          <span className="text-ink">4 agents · 3 humans</span>
        </div>
      </div>
    </div>
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
            "radial-gradient(ellipse 80% 60% at 20% 10%, rgba(249,115,22,0.09), transparent 60%)",
        }}
      />
      <div className="relative z-10 mx-auto grid max-w-[1200px] grid-cols-1 gap-12 px-7 pb-8 pt-20 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:items-center lg:gap-16 lg:pb-16 lg:pt-28">
        <div>
          <ScrollLink
            to="#install"
            className="inline-flex items-center gap-2.5 rounded-full border border-border bg-white/70 py-[5px] pl-[5px] pr-3.5 text-[12px] text-dim shadow-sm transition hover:border-brand/40 hover:text-ink"
          >
            <span className="rounded-full bg-brand px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-white">
              New
            </span>
            <span>Now works with Openclaw</span>
            <span className="font-mono text-muted">→</span>
          </ScrollLink>

          <h1 className="mt-7 text-balance font-display text-[clamp(44px,6.2vw,80px)] font-black leading-[0.95] tracking-[-0.045em] text-ink">
            <span className="text-brand">Agent memory</span>
            <br />
            for your repos.
          </h1>

          <p className="mt-7 max-w-[520px] text-[18px] leading-[1.55] text-foreground">
            Stash is the hive mind for your team&apos;s coding agents. Every
            session, decision, and search flows into one shared brain, so the
            next agent that touches your repo already knows what yours learned.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <ScrollLink
              to="#install"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-[18px] text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Install Stash <span className="font-mono">→</span>
            </ScrollLink>
            <Link
              href="https://github.com/Fergana-Labs/stash"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-border bg-transparent px-[18px] text-[14px] font-medium text-ink transition hover:border-ink"
            >
              View on GitHub
            </Link>
          </div>

          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 font-mono text-[11px] uppercase tracking-[0.08em] text-muted">
            <span className="inline-flex items-center gap-2">
              <span className="h-[6px] w-[6px] rounded-full bg-current opacity-50" />
              MIT licensed
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-[6px] w-[6px] rounded-full bg-current opacity-50" />
              Self-hostable
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-[6px] w-[6px] rounded-full bg-current opacity-50" />
              Postgres + pgvector
            </span>
          </div>
        </div>
        <HeroFeed />
      </div>
    </section>
  );
}

function Logos() {
  const tools = [
    { name: "Claude Code", src: "/logos/anthropic.svg" },
    { name: "Cursor", src: "/logos/cursor.png" },
    { name: "Codex", src: "/logos/openai.svg" },
    { name: "OpenCode", src: "/logos/opencode.svg" },
    { name: "Openclaw", src: "/logos/openclaw.png" },
  ];
  return (
    <div className="border-y border-border-subtle bg-surface">
      <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-8 px-7 py-6">
        <span className="shrink-0 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          Works with
        </span>
        <div className="flex flex-wrap items-center gap-x-10 gap-y-4 text-dim">
          {tools.map((t) => (
            <span
              key={t.name}
              className="inline-flex items-center gap-2.5 whitespace-nowrap font-display text-[17px] font-bold tracking-[-0.02em] text-ink"
              title={t.name}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={t.src}
                alt={t.name}
                className="h-6 w-6 shrink-0 object-contain"
              />
              <span>{t.name}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function InstallSlab() {
  return (
    <section id="install" className="border-b border-border-subtle">
      <div className="mx-auto max-w-[1200px] px-7 py-24">
        <div className="grid grid-cols-1 items-center gap-10 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] md:gap-[72px]">
          <div>
            <EyebrowDot>Install</EyebrowDot>
            <h2 className="mt-4 font-display text-[clamp(28px,3.2vw,40px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
              One command.
            </h2>
            <p className="mt-4 max-w-[440px] text-[16px] leading-[1.6] text-foreground">
              Automatic setup. No yaml, no manual plugin wiring. The CLI detects
              your agents and wires them up for you.
            </p>
            <p className="mt-4 max-w-[440px] text-[16px] leading-[1.6] text-foreground">
              Use our managed service and be streaming in a minute, or self-host
              on your own infra if you&apos;d rather keep every session in your
              own Postgres.
            </p>
          </div>
          <div
            className="overflow-hidden rounded-[14px] border border-white/5 bg-inverted"
            style={{ boxShadow: "var(--shadow-terminal)" }}
          >
            <div className="flex items-center justify-between border-b border-white/5 px-3.5 py-2.5">
              <div className="flex items-center gap-3">
                <div className="flex gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                  <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                  <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                </div>
                <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-on-inverted-dim">
                  install.sh
                </span>
              </div>
              <CopyButton
                value={INSTALL_COMMAND}
                label="copy"
                copiedLabel="copied ✓"
                className="inline-flex h-[26px] items-center rounded-md border border-white/10 bg-transparent px-2.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-on-inverted-dim transition hover:border-white/30 hover:text-white data-[copied=true]:border-[rgba(34,197,94,0.5)] data-[copied=true]:text-[#22C55E]"
              />
            </div>
            <div className="overflow-x-auto px-5 py-6 font-mono text-[14px] leading-[1.75] text-on-inverted">
              <div className="whitespace-pre">
                <span className="mr-2.5 select-none text-brand">$</span>
                <span className="text-white">{INSTALL_COMMAND}</span>
              </div>
              <div className="whitespace-pre text-on-inverted-dim">
                » installing stash cli  v0.9.2
              </div>
              <div className="whitespace-pre">
                <span className="text-on-inverted-dim">» scope      </span>
                <span className="text-[#22C55E]">✓ team/fergana</span>
              </div>
              <div className="whitespace-pre">
                <span className="text-on-inverted-dim">» sign-in    </span>
                <span className="text-[#22C55E]">✓ sam@fergana.dev</span>
              </div>
              <div className="whitespace-pre">
                <span className="text-on-inverted-dim">» workspace  </span>
                <span className="text-[#22C55E]">✓ backend-api</span>
              </div>
              <div className="whitespace-pre">
                <span className="text-on-inverted-dim">» plugin     </span>
                <span style={{ color: "var(--agent)" }}>claude-code</span>
                <span className="text-on-inverted-dim"> · </span>
                <span style={{ color: "var(--agent)" }}>cursor</span>
                <span className="text-on-inverted-dim"> · </span>
                <span style={{ color: "var(--agent)" }}>codex</span>
              </div>
              <div className="whitespace-pre">
                <span className="text-[#22C55E]">✓ ready.</span>
                <span className="text-on-inverted-dim"> your team&apos;s memory is streaming.</span>
              </div>
              <div className="whitespace-pre">
                <span className="mr-2.5 select-none text-brand">$</span>
                <span
                  className="inline-block h-[15px] w-2 align-[-2px] bg-brand"
                  style={{ animation: "cursor-blink 1.2s steps(2) infinite" }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Problem() {
  const asks = [
    { i: "01", q: "“Why did Sam bump the rate limit from 100 to 500?”", by: "rex · agent" },
    { i: "02", q: "“Has anyone already tried fixing the memory leak in auth?”", by: "scout · agent" },
    { i: "03", q: "“Is anyone else currently working on the API gateway?”", by: "nova · agent" },
    { i: "04", q: "“What pattern did we land on for background workers last sprint?”", by: "rex · agent" },
  ];
  return (
    <section className="border-b border-border-subtle py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <EyebrowDot>The problem</EyebrowDot>
        <h2 className="mt-4 max-w-[980px] text-balance font-display text-[clamp(40px,5.2vw,68px)] font-black leading-[1.02] tracking-[-0.04em] text-ink">
          Every coding agent on your team{" "}
          <span className="relative inline-block">
            starts from zero.
            <span
              aria-hidden
              className="pointer-events-none absolute left-[-4px] right-[-4px] top-[54%] h-[0.16em] -skew-y-[2deg] bg-brand"
            />
          </span>
        </h2>
        <div className="mt-12 grid grid-cols-1 gap-8 text-[17px] leading-[1.6] text-foreground md:grid-cols-2 md:gap-14">
          <p>
            Your agent just debugged a flaky auth test. An hour later, a
            teammate&apos;s agent hits the same test and starts from scratch.
            Nobody told it what you learned.
          </p>
          <p>
            Multiply that across a week of work: half the team is reinventing
            the same fixes, rediscovering the same gotchas, and asking each
            other&apos;s humans for context their agents could have read
            themselves.
          </p>
        </div>

        <div className="mt-20 border-t border-border">
          <p className="py-6 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
            Questions your agent can now ask, and answer
          </p>
          {asks.map((a) => (
            <div
              key={a.i}
              className="grid grid-cols-[auto_1fr_auto] items-baseline gap-6 border-b border-border py-7"
            >
              <span className="font-mono text-[11px] tracking-[0.14em] text-muted">{a.i}</span>
              <span className="font-display text-[clamp(20px,2.2vw,28px)] font-medium leading-[1.3] tracking-[-0.02em] text-ink">
                {a.q}
              </span>
              <span className="font-mono text-[11px] text-dim">{a.by}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function StreamViz() {
  const lines: { r: "agent" | "human"; t: string; a: string; l: string; new?: boolean }[] = [
    { r: "agent", t: "14:02", a: "tool_call", l: "read_file(auth.py)" },
    { r: "agent", t: "14:02", a: "edit", l: "session_refresh.py" },
    { r: "human", t: "14:03", a: "review", l: "pr/#482" },
    { r: "agent", t: "14:04", a: "test", l: "pytest auth/", new: true },
  ];
  return (
    <div className="flex flex-col gap-1.5 font-mono text-[11px]">
      {lines.map((x, i) => (
        <div
          key={i}
          className={"flex items-center gap-2 " + (x.new ? "text-ink" : "text-dim")}
        >
          <span className="text-[10px] text-muted">{x.t}</span>
          <span
            className="h-[6px] w-[6px] shrink-0 rounded-full"
            style={{ background: x.r === "agent" ? "var(--agent)" : "var(--human)" }}
          />
          <span className="text-ink">{x.a}</span>
          <span>{x.l}</span>
        </div>
      ))}
    </div>
  );
}

function CurateViz() {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink">
        auth-patterns
        <span
          className="rounded px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.08em] text-brand"
          style={{ background: "var(--brand-soft)" }}
        >
          root
        </span>
      </div>
      <div className="relative ml-4 flex items-center rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink before:absolute before:left-[-10px] before:top-1/2 before:h-px before:w-2 before:bg-border">
        session-refresh 401 race
      </div>
      <div className="relative ml-4 flex items-center rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink before:absolute before:left-[-10px] before:top-1/2 before:h-px before:w-2 before:bg-border">
        rate-limits · 500/min
      </div>
      <div className="flex items-center justify-between rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink">
        memory-leak-v2
        <span
          className="rounded px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.08em] text-brand"
          style={{ background: "var(--brand-soft)" }}
        >
          new
        </span>
      </div>
    </div>
  );
}

function SearchViz() {
  const sources: [string, string][] = [
    ["history/rex:14:02", "62%"],
    ["notebooks/auth-patterns", "21%"],
    ["files/gateway.py", "11%"],
  ];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11.5px] text-ink">
        <span className="font-mono text-[11px] text-brand">/stash</span>
        why was the rate-limit raised?
      </div>
      <div className="flex flex-col gap-1 font-mono text-[10.5px] text-dim">
        {sources.map(([p, pct]) => (
          <div key={p} className="flex justify-between">
            <span className="text-ink">{p}</span>
            <span className="text-brand">{pct}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function HowItWorks() {
  const steps = [
    {
      n: "01",
      pill: "Stream",
      title: "Every session flows into a shared store.",
      body: "Prompts, tool calls, and session summaries push to your workspace’s history as they happen. Nothing to remember to save.",
      viz: <StreamViz />,
    },
    {
      n: "02",
      pill: "Curate",
      title: "A curation agent turns noise into a wiki.",
      body: "On SessionEnd, stash:sleep reads recent history and organizes it into notebooks with [[backlinks]] and a page graph. Sleep-time compute, not session time.",
      viz: <CurateViz />,
    },
    {
      n: "03",
      pill: "Search",
      title: "Every agent queries the whole team's work.",
      body: "stash search runs a cross-resource agentic loop over files, history, notebooks, tables, and chats. Your agent answers with sources, not hallucinations.",
      viz: <SearchViz />,
    },
  ];
  return (
    <section id="how" className="border-b border-border-subtle bg-surface py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="flex max-w-[880px] flex-col gap-4">
          <EyebrowDot>How it works</EyebrowDot>
          <h2 className="font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
            Stream. Curate. Search.
            <br />
            <span className="font-medium text-dim">Nobody starts from zero.</span>
          </h2>
        </div>
        <div className="mt-16 grid grid-cols-1 gap-5 lg:grid-cols-3">
          {steps.map((s) => (
            <div
              key={s.n}
              className="flex min-h-[380px] flex-col rounded-[14px] border border-border bg-background p-6 transition-colors hover:border-brand"
            >
              <div className="mb-5 flex items-center justify-between">
                <span className="font-mono text-[11px] tracking-[0.14em] text-muted">{s.n}</span>
                <span
                  className="rounded px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-brand"
                  style={{ background: "var(--brand-soft)" }}
                >
                  {s.pill}
                </span>
              </div>
              <div className="mb-5 min-h-[150px] shrink-0 rounded-[10px] border border-border-subtle bg-raised p-3.5">
                {s.viz}
              </div>
              <h3 className="font-display text-[20px] font-bold tracking-[-0.015em] text-ink">
                {s.title}
              </h3>
              <p className="mt-2.5 text-[14.5px] leading-[1.6] text-dim">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SearchDemo() {
  const steps = [
    { t: "scanned team history", ms: "42ms" },
    { t: "queried notebook graph", ms: "81ms" },
    { t: "pulled gateway.py blame", ms: "104ms" },
    { t: "reranked 8 sources", ms: "22ms" },
  ];
  return (
    <section id="search" className="border-b border-border-subtle py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="flex max-w-[880px] flex-col gap-4">
          <EyebrowDot>One query, every source</EyebrowDot>
          <h2 className="font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
            <span className="font-medium text-dim">Your agent asks.</span>
            <br />
            Stash answers with receipts.
          </h2>
          <p className="max-w-[620px] text-[18px] leading-[1.55] text-dim">
            stash search runs an agentic loop across files, history, notebooks,
            tables, and chats. Every answer arrives with sources attached.
          </p>
        </div>
        <div
          className="mt-12 overflow-hidden rounded-2xl border border-white/5 bg-inverted"
          style={{ boxShadow: "var(--shadow-terminal)" }}
        >
          <div className="flex items-center gap-3.5 border-b border-white/5 px-5 py-3.5">
            <div className="flex items-center gap-2.5 font-mono text-[13px] text-white">
              <span className="text-brand">›</span>
              <span>stash search</span>
            </div>
            <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.14em] text-on-inverted-dim">
              agentic loop · 5 resources
            </span>
          </div>
          <div className="px-5 py-5 md:px-6">
            <p className="mb-6 font-display text-[clamp(22px,2.6vw,30px)] font-bold leading-[1.25] tracking-[-0.02em] text-white">
              &ldquo;Why did we raise the gateway rate-limit from 100 to 500?&rdquo;
            </p>
            <div className="grid grid-cols-1 gap-2.5 font-mono text-[12px] sm:grid-cols-2 sm:gap-x-8 sm:gap-y-2.5">
              {steps.map((s, i) => (
                <div
                  key={i}
                  className="grid grid-cols-[14px_1fr_auto] items-baseline gap-2.5 border-b border-dashed border-white/5 py-2 text-on-inverted-dim"
                >
                  <span className="text-[#22C55E]">✓</span>
                  <span className="text-on-inverted">{s.t}</span>
                  <span className="text-[10.5px] tracking-[0.08em] text-muted">{s.ms}</span>
                </div>
              ))}
            </div>
            <div
              className="mt-6 rounded-[10px] border p-5"
              style={{
                background: "rgba(249,115,22,0.06)",
                borderColor: "rgba(249,115,22,0.2)",
              }}
            >
              <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-brand">
                Answer
              </p>
              <p className="text-[15px] leading-[1.6] text-white">
                Sam raised it on Tue to unblock the batch-import flow. The old
                limit was throttling legitimate imports from Shopify partners.
                The change is safe because requests are authenticated and
                per-tenant, not global.{" "}
                <span className="font-mono text-[11.5px] text-brand">history/sam:tue-14:22</span>,{" "}
                <span className="font-mono text-[11.5px] text-brand">notebooks/gateway-limits</span>
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Features() {
  const items = [
    {
      i: "H",
      h: "Shared history",
      p: "Every prompt and tool call streams to a team-wide event log. Searchable, filterable, attributable.",
      tags: ["events", "per-agent", "replay"],
    },
    {
      i: "W",
      h: "Wiki notebooks",
      p: "Rich collaborative pages with [[backlinks]], page graph, and pgvector semantic search, curated by a sleep-time agent.",
      tags: ["backlinks", "graph", "semantic"],
    },
    {
      i: "S",
      h: "Agentic search",
      p: "stash search runs a cross-resource loop over every surface in the workspace. One query, every source, with receipts.",
      tags: ["cross-source", "cited", "streaming"],
    },
    {
      i: "V",
      h: "Visualizations",
      p: "See your team's memory as it forms: embedding projections, page graphs, activity timelines, and knowledge-density maps you can actually look at.",
      tags: ["embeddings", "graph", "timeline"],
    },
    {
      i: "R",
      h: "Real-time rooms",
      p: "Agents and humans chat side-by-side in workspace channels. Coordinate, hand off, and unblock each other, all in one place.",
      tags: ["channels", "presence", "handoff"],
    },
    {
      i: "P",
      h: "Shareable pages",
      p: "Publish research, reports, and dashboards as HTML anyone with a link can view. No login walls between teams.",
      tags: ["public", "embeds", "html"],
    },
  ];
  return (
    <section id="features" className="border-b border-border-subtle py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="flex max-w-[880px] flex-col gap-4">
          <EyebrowDot>What&apos;s inside</EyebrowDot>
          <h2 className="font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
            Everything one agent should know,
            <br />
            <span className="font-medium text-dim">every agent does.</span>
          </h2>
        </div>
        <div className="mt-16 grid grid-cols-1 border-t border-border sm:grid-cols-2 lg:grid-cols-3">
          {items.map((f, i) => {
            const col = i % 3;
            const isLastCol = col === 2;
            return (
              <div
                key={f.h}
                className={
                  "flex min-h-[200px] flex-col gap-2.5 border-b border-border py-8 " +
                  (isLastCol ? "lg:border-r-0" : "lg:border-r") +
                  " " +
                  (i % 2 === 1 ? "sm:border-r-0 sm:pl-8" : "sm:border-r sm:pr-8") +
                  " lg:px-8 lg:first:pl-0 " +
                  (col === 0 ? "lg:pl-0" : "") +
                  (isLastCol ? " lg:pr-0" : "")
                }
              >
                <span className="mb-1 grid h-7 w-7 place-items-center rounded-md bg-raised font-mono text-[12px] font-bold text-ink">
                  {f.i}
                </span>
                <h3 className="font-display text-[19px] font-bold tracking-[-0.01em] text-ink">
                  {f.h}
                </h3>
                <p className="text-[14.5px] leading-[1.6] text-dim">{f.p}</p>
                <div className="mt-auto flex flex-wrap gap-1.5 pt-3 font-mono text-[10.5px] uppercase tracking-[0.08em] text-muted">
                  {f.tags.map((t) => (
                    <span key={t} className="rounded bg-raised px-1.5 py-0.5">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function ClosingCTA() {
  return (
    <section className="border-b border-border-subtle bg-surface py-32 text-center">
      <div className="mx-auto max-w-[1200px] px-7">
        <h2 className="text-balance font-display text-[clamp(44px,5.4vw,80px)] font-black leading-[0.98] tracking-[-0.045em] text-ink">
          Stop starting
          <br />
          <span className="text-brand">from zero.</span>
        </h2>
        <p className="mx-auto mt-6 max-w-[520px] text-[17px] text-dim">
          Your team&apos;s agents are already writing code. Give them somewhere
          to remember it.
        </p>
        <div className="mt-9 flex flex-wrap justify-center gap-3">
          <ScrollLink
            to="#install"
            className="inline-flex h-10 items-center rounded-lg bg-brand px-[18px] text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
          >
            Install Stash →
          </ScrollLink>
          <Link
            href="/docs/quickstart"
            className="inline-flex h-10 items-center rounded-lg border border-border bg-transparent px-[18px] text-[14px] font-medium text-ink transition hover:border-ink"
          >
            Read the quickstart
          </Link>
        </div>
        <p className="mx-auto mt-8 font-mono text-[11.5px] uppercase tracking-[0.1em] text-muted">
          MIT · Self-hostable
        </p>
      </div>
    </section>
  );
}

function Footer() {
  const columns = [
    {
      h: "Product",
      links: [
        ["Install", "#install"],
        ["How it works", "#how"],
        ["Features", "#features"],
        ["Changelog", "/docs"],
      ],
    },
    {
      h: "Resources",
      links: [
        ["Docs", "/docs"],
        ["Quickstart", "/docs/quickstart"],
        ["Use cases", "/docs"],
        ["Architecture", "/docs"],
      ],
    },
    {
      h: "Company",
      links: [
        ["GitHub", "https://github.com/Fergana-Labs/stash"],
        ["Discord", "#"],
        ["Blog", "#"],
        ["Contact", "#"],
      ],
    },
  ];
  return (
    <footer className="border-t border-border-subtle">
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-10 px-7 pb-8 pt-14 sm:grid-cols-[1.2fr_1fr_1fr_1fr] sm:gap-12">
        <div>
          <div className="flex items-center gap-2.5 font-display text-[26px] font-black tracking-[-0.03em] text-ink">
            <Logo size={30} />
            stash
          </div>
          <p className="mt-3 max-w-[320px] text-[13.5px] leading-[1.55] text-dim">
            Shared memory for teams of AI coding agents. Open source, MIT
            licensed, self-hostable.
          </p>
        </div>
        {columns.map((col) => (
          <div key={col.h}>
            <h4 className="mb-3.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
              {col.h}
            </h4>
            {col.links.map(([label, href]) =>
              href.startsWith("#") ? (
                <ScrollLink
                  key={label}
                  to={href}
                  className="block py-1 text-[13.5px] text-foreground transition hover:text-brand"
                >
                  {label}
                </ScrollLink>
              ) : (
                <Link
                  key={label}
                  href={href}
                  className="block py-1 text-[13.5px] text-foreground transition hover:text-brand"
                >
                  {label}
                </Link>
              ),
            )}
          </div>
        ))}
      </div>
      <div className="border-t border-border-subtle">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-7 py-5 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
          <span>© 2026 Fergana Labs</span>
          <span>MIT · v0.9.2</span>
        </div>
      </div>
    </footer>
  );
}
