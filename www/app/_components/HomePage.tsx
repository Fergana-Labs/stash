import Link from "next/link";
import type { ReactNode } from "react";

import AppRedirectForSignedInUsers from "./AppRedirectForSignedInUsers";
import { INTEGRATIONS, integrationIcon } from "./BrandIcons";
import CtaPair from "./CtaPair";
import HeroTerminal from "./HeroTerminal";
import Logo from "./Logo";
import ScrollLink from "./ScrollLink";
import SiteHeader from "./SiteHeader";
import Texture from "./Texture";
import VisualizationsShowcase from "./VisualizationsShowcase";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";
const CALL_URL = "/contact-sales";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <AppRedirectForSignedInUsers appUrl={APP_URL} />
      <SiteHeader />
      <Hero />
      <Logos />
      <Problem />
      <HowItWorks />
      <KarpathyQuote />
      <Comparisons />
      <VisualizationsShowcase />
      <Features />
      <CliAndPlugin />
      <Proof />
      <OpenSource />
      <Pricing />
      <EnterpriseStrip />
      <ClosingCTA />
      <Footer />
    </main>
  );
}

// The signature mono kicker — [ SECTION.NAME ] — defined once in globals.css
// (.kicker) and reused as every section's eyebrow.
function Kicker({ children }: { children: ReactNode }) {
  return <p className="kicker">{children}</p>;
}

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

type StashItem = { kind: "page" | "session" | "table"; label: string; meta: string };

function StashKindTag({ kind }: { kind: StashItem["kind"] }) {
  const palette: Record<StashItem["kind"], { bg: string; fg: string }> = {
    page: { bg: "rgba(249,115,22,0.10)", fg: "var(--brand)" },
    session: { bg: "var(--agent-soft)", fg: "var(--agent)" },
    table: { bg: "var(--human-soft)", fg: "var(--human)" },
  };
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[9.5px] font-medium uppercase leading-none tracking-[0.12em]"
      style={{ background: palette[kind].bg, color: palette[kind].fg }}
    >
      {kind}
    </span>
  );
}

export function HeroFunnel() {
  return (
    <div className="relative w-full max-w-[565px]">
      <div
        className="overflow-hidden rounded-[18px] border border-border-subtle bg-background"
        style={{
          aspectRatio: "1086 / 1280",
          boxShadow:
            "rgba(15, 23, 42, 0.04) 0px 1px 2px 0px, rgba(15, 23, 42, 0.10) 0px 24px 48px -24px",
          WebkitMaskImage:
            "linear-gradient(to bottom, black 0%, black 88%, transparent 100%)",
          maskImage:
            "linear-gradient(to bottom, black 0%, black 88%, transparent 100%)",
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/hero-funnel.png"
          alt="A blurred fan of customer-feedback sources funnelling into a single, crisp Stash article that synthesizes the recurring asks."
          width={1086}
          height={1676}
          className="block h-full w-full object-cover object-top"
        />
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-border-subtle">
      <Texture className="h-[760px]" fade="top" />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 z-0 h-[680px]"
        style={{
          background:
            "radial-gradient(ellipse 80% 60% at 18% 8%, rgba(249,115,22,0.10), transparent 60%)",
        }}
      />
      <div className="relative z-10 mx-auto max-w-[1200px] px-7 pb-16 pt-20 lg:pb-24 lg:pt-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1.02fr)_minmax(0,0.98fr)] lg:items-center lg:gap-16">
          <div>
            <h1 className="text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.0] tracking-[-0.035em] text-ink">
              Company Brain for agents{" "}
              <span className="text-brand">and humans.</span>
            </h1>

            <p className="mt-7 max-w-[560px] text-[18px] leading-[1.55] text-foreground">
              Stash connects all your tools and captures every agent session,
              builds them into one context graph, and serves it to your agents as
              a virtual filesystem (VFS) they can read, search, and write back
              into.
            </p>

            <div className="mt-9">
              <CtaPair />
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[12px] text-dim">
              <Link
                href="https://github.com/Fergana-Labs/stash"
                className="inline-flex items-center gap-2 transition hover:text-ink"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                  <path d="M12 .5C5.65.5.5 5.65.5 12a11.5 11.5 0 0 0 7.86 10.92c.57.11.78-.25.78-.55v-1.94c-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.47.11-3.07 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.63 1.6.23 2.78.12 3.07.74.81 1.19 1.84 1.19 3.1 0 4.41-2.69 5.38-5.26 5.67.41.35.77 1.05.77 2.12v3.14c0 .3.21.67.79.55A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
                </svg>
                Open source
              </Link>
              <span className="text-border">·</span>
              <span>MIT licensed</span>
              <span className="text-border">·</span>
              <span>Self-hostable</span>
            </div>
          </div>
          <HeroTerminal />
        </div>
      </div>
    </section>
  );
}

export function Logos() {
  const tools = [
    { name: "Claude Code", src: "/logos/anthropic.svg" },
    { name: "Cursor", src: "/logos/cursor.png" },
    { name: "Codex", src: "/logos/openai.svg" },
    { name: "OpenCode", src: "/logos/opencode.svg" },
    { name: "Openclaw", src: "/logos/openclaw.png" },
  ];
  return (
    <div className="border-y border-border-subtle bg-surface">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-5 px-7 py-7">
        <LogoRow label="Plugs into">
          {tools.map((t) => (
            <span
              key={t.name}
              className="inline-flex shrink-0 items-center gap-2.5 whitespace-nowrap font-display text-[17px] font-bold tracking-[-0.02em] text-ink"
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
        </LogoRow>
        <div className="border-t border-border-subtle pt-5">
          <LogoRow label="Connects to" trailer="and many more">
            {INTEGRATIONS.map((it) => (
              <span
                key={it.provider}
                className="inline-flex shrink-0 items-center gap-2.5 whitespace-nowrap font-display text-[16px] font-bold tracking-[-0.02em] text-ink"
                title={it.name}
              >
                <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center">
                  {integrationIcon(it.provider, 22)}
                </span>
                <span>{it.name}</span>
              </span>
            ))}
          </LogoRow>
        </div>
      </div>
    </div>
  );
}

// One-line logo strip: the list scrolls horizontally instead of wrapping,
// and the optional trailer ("and many more") stays pinned and visible.
function LogoRow({
  label,
  trailer,
  children,
}: {
  label: string;
  trailer?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-x-6">
      <span className="w-[96px] shrink-0 whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
        {label}
      </span>
      <div
        className="flex min-w-0 flex-1 items-center gap-x-8 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        style={{
          maskImage:
            "linear-gradient(to right, black calc(100% - 32px), transparent)",
        }}
      >
        {children}
      </div>
      {trailer ? (
        <span className="shrink-0 whitespace-nowrap font-display text-[15px] font-bold tracking-[-0.02em] text-dim">
          {trailer}
        </span>
      ) : null}
    </div>
  );
}

function Problem() {
  return (
    <section className="border-b border-border-subtle py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <Kicker>The problem</Kicker>
        <h2 className="mt-4 max-w-[980px] text-balance font-display text-[clamp(38px,5vw,64px)] font-bold leading-[1.04] tracking-[-0.035em] text-ink">
          Your agent is a clueless genius.{" "}
          <span className="text-dim">It forgets everything by{" "}</span>
          <span className="text-brand">tomorrow.</span>
        </h2>
        <div className="mt-12 grid grid-cols-1 gap-8 text-[17px] leading-[1.6] text-foreground md:grid-cols-2 md:gap-14">
          <p>
            Every Claude, Cursor, or Codex run generates pages of work:
            transcripts, plans, the decisions it reasoned through, the files it
            wrote. Most of it evaporates the moment the session closes, so the
            next run starts cold and re-derives what you already solved.
          </p>
          <p>
            Stash fixes that. It connects to all your data, from GitHub and Drive
            to Gmail, Notion, and Slack, and captures every session into one
            agent-native Drive your agents can read, search, and write back into.
            Memory that builds itself, shared across every agent and teammate.
          </p>
        </div>
      </div>
    </section>
  );
}

type Comparison = { tool: string; theyDo: string; stashAdds: string };
const COMPARISONS: Comparison[] = [
  {
    tool: "Obsidian",
    theyDo:
      "A single-user Markdown vault. No real collaboration, and nothing richer than .md.",
    stashAdds:
      "Real-time editing across humans and agents, with HTML, tables, PDFs, and any file type.",
  },
  {
    tool: "Notion",
    theyDo: "Pages for humans. Agents can't browse it like a real filesystem.",
    stashAdds:
      "A virtual filesystem the CLI and MCP expose to agents natively.",
  },
  {
    tool: "Google Drive",
    theyDo: "Files for humans. No structure agents can reason over.",
    stashAdds: "An agent-readable shell over your files, pages, and sessions.",
  },
  {
    tool: "GitHub",
    theyDo:
      "Editing a doc means a clone, a branch, a PR. Fine for source code, painful for anything else.",
    stashAdds:
      "Edit pages in the browser. Agents read and write them directly.",
  },
  {
    tool: "Observability tools",
    theyDo:
      "Built to monitor production agents and improve them. The output is traces and dashboards, not work product.",
    stashAdds:
      "Where the agent's output is the work product, not telemetry to watch.",
  },
  {
    tool: "AI memory tools",
    theyDo:
      "Per-agent memory in a black box. Doesn't help the human or agent next to you.",
    stashAdds: "A shared space humans can read and edit, in real time.",
  },
];

export function Comparisons() {
  return (
    <section className="border-b border-border-subtle bg-surface py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="flex max-w-[880px] flex-col gap-4">
          <Kicker>Where Stash fits</Kicker>
          <h2 className="font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
            Built where your current tools stop.
            <br />
            <span className="font-medium text-dim">
              Each does part of the job. None gives humans and agents the same
              space.
            </span>
          </h2>
        </div>
        <div className="mt-14 grid grid-cols-1 gap-px overflow-hidden rounded-[14px] border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {COMPARISONS.map((c) => (
            <div key={c.tool} className="flex flex-col gap-3 bg-background p-6">
              <div className="flex items-center justify-between">
                <span className="font-display text-[16px] font-bold tracking-[-0.01em] text-ink">
                  {c.tool}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                  vs stash
                </span>
              </div>
              <p className="text-[13.5px] leading-[1.55] text-dim">{c.theyDo}</p>
              <p className="mt-auto border-t border-border-subtle pt-3 text-[13.5px] leading-[1.55] text-ink">
                <span className="mr-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-brand">
                  Stash adds
                </span>
                {c.stashAdds}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function StreamViz() {
  const lines: { r: "agent" | "human"; t: string; a: string; l: string; new?: boolean }[] = [
    { r: "agent", t: "14:02", a: "tool_call", l: "read_file(auth.py)" },
    { r: "agent", t: "14:02", a: "wrote", l: "plan.md" },
    { r: "human", t: "14:03", a: "review", l: "pr/#482" },
    { r: "agent", t: "14:04", a: "session", l: "uploaded · 312 events", new: true },
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

export function FilesViz() {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink">
        auth-patterns/
        <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-muted">
          folder
        </span>
      </div>
      <div className="relative ml-4 flex items-center rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink before:absolute before:left-[-10px] before:top-1/2 before:h-px before:w-2 before:bg-border">
        session-refresh.md
      </div>
      <div className="relative ml-4 flex items-center rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink before:absolute before:left-[-10px] before:top-1/2 before:h-px before:w-2 before:bg-border">
        rate-limits.html
      </div>
      <div className="flex items-center justify-between rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink">
        experiments
        <span
          className="rounded px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.08em]"
          style={{ background: "var(--human-soft)", color: "var(--human)" }}
        >
          table
        </span>
      </div>
    </div>
  );
}

export function StashViz() {
  const items: [StashItem["kind"], string][] = [
    ["page", "session-refresh.md"],
    ["page", "rate-limits.html"],
    ["session", "rate-limit-investigation"],
  ];
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink">
        <span className="flex items-center gap-2">
          <span
            className="inline-flex h-4 w-4 items-center justify-center rounded font-mono text-[9px] font-bold text-white"
            style={{ background: "var(--brand)" }}
          >
            S
          </span>
          Auth Patterns · Q2
        </span>
        <span
          className="rounded px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.08em] text-brand"
          style={{ background: "var(--brand-soft)" }}
        >
          public
        </span>
      </div>
      {items.map(([kind, label]) => (
        <div
          key={label}
          className="relative ml-4 flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink before:absolute before:left-[-10px] before:top-1/2 before:h-px before:w-2 before:bg-border"
        >
          <StashKindTag kind={kind} />
          <span className="truncate">{label}</span>
        </div>
      ))}
    </div>
  );
}

export type HowItWorksStep = {
  n: string;
  pill: string;
  title: string;
  body: string;
  viz: ReactNode;
};

export function SourcesViz() {
  const rows = [
    { provider: "github", name: "GitHub" },
    { provider: "slack", name: "Slack" },
    { provider: "gong", name: "Gong" },
    { provider: "notion", name: "Notion" },
  ];
  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((r) => (
        <div
          key={r.provider}
          className="flex items-center justify-between rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-ink"
        >
          <span className="flex items-center gap-2">
            <span className="inline-flex h-4 w-4 items-center justify-center">
              {integrationIcon(r.provider, 14)}
            </span>
            {r.name}
          </span>
          <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-[#22C55E]">
            synced
          </span>
        </div>
      ))}
    </div>
  );
}

const DEFAULT_HOW_STEPS: HowItWorksStep[] = [
  {
    n: "01",
    pill: "Connect",
    title: "Connect any data source.",
    body: "GitHub, Drive, Gmail, Notion, Slack, Jira, Gong and more. One easy connection per source, through any integration, and every agent you run can read all of them.",
    viz: <SourcesViz />,
  },
  {
    n: "02",
    pill: "Remember",
    title: "Memory that builds itself.",
    body: "Every agent session, including prompts, tool calls, and artifacts, streams in automatically and becomes shared, retrievable memory. Your agents remember what they did instead of starting from zero each run.",
    viz: <StreamViz />,
  },
  {
    n: "03",
    pill: "VFS",
    title: "A virtual filesystem agents speak.",
    body: "Your whole Stash mounts as a virtual filesystem (VFS) agents ls, find, and rg through the CLI and MCP. Humans and agents edit the same files at the same time, synced live, so everyone works from one copy.",
    viz: <FilesViz />,
  },
];

// The message-test variant pages pass their own title/steps so the section
// tells the story of the message under test.
export function HowItWorks({
  title = "Connect. Remember. Create.",
  subtitle = "One space, two kinds of writer.",
  steps = DEFAULT_HOW_STEPS,
}: {
  title?: string;
  subtitle?: string;
  steps?: HowItWorksStep[];
}) {
  return (
    <section id="how" className="border-b border-border-subtle bg-surface py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="flex max-w-[880px] flex-col gap-4">
          <Kicker>How.it.works</Kicker>
          <h2 className="font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
            {title}
            <br />
            <span className="font-medium text-dim">{subtitle}</span>
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
              <div className="mb-5 flex h-[176px] shrink-0 flex-col justify-center rounded-[10px] border border-border-subtle bg-raised p-3.5">
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

function KarpathyQuote() {
  return (
    <section className="border-b border-border-subtle py-28 md:py-36">
      <div className="mx-auto max-w-[1100px] px-7">
        <Kicker>The category</Kicker>
        <figure className="mt-8">
          <blockquote className="font-display text-[clamp(26px,3.4vw,42px)] font-medium leading-[1.25] tracking-[-0.02em] text-ink">
            <span className="text-dim">“raw data from a number of sources is collected, then compiled by an LLM into a .md knowledge base, then operated on by various CLIs by the LLM to do Q&amp;A and to incrementally enhance it… </span>
            <span className="text-ink">I think there is room here for an incredible new product instead of a hacky collection of scripts.”</span>
          </blockquote>
          <figcaption className="mt-8 flex items-center gap-3 font-mono text-[12px] uppercase tracking-[0.14em] text-muted">
            <span className="h-px w-8 bg-border" />
            Andrej Karpathy · on LLM knowledge bases
          </figcaption>
        </figure>
        <p className="mt-10 max-w-[680px] text-[18px] leading-[1.6] text-foreground">
          Stash is that product. A company brain humans and agents both write
          into — not a stack of shell scripts wrapped around a folder of
          markdown.
        </p>
        <div className="mt-16 border-t border-border-subtle pt-12">
          <Kicker>Use.cases</Kicker>
          <h3 className="mt-4 font-display text-[clamp(24px,2.8vw,36px)] font-bold tracking-[-0.02em] text-ink">
            Built for —
          </h3>
          <ul className="mt-8 flex flex-col gap-5 font-mono text-[14.5px] leading-[1.55]">
            {[
              ["Engineering live docs", "coding-agent plans, ADRs, and design notes that stay current"],
              ["Company brain", "the shared context every agent and teammate reads from"],
              ["Research knowledge base", "long-running PKBs with sources, transcripts, and tables"],
              ["Ops playbooks", "release runbooks and on-call procedures"],
              ["Brand voice", "editorial guidelines and copy standards agents write to"],
              ["Personal knowledge management", "notes, drafts, and scratch files for a single operator"],
            ].map(([who, what]) => (
              <li
                key={who}
                className="grid grid-cols-1 items-baseline gap-1 md:grid-cols-[320px_auto_minmax(0,1fr)] md:gap-4"
              >
                <span className="font-semibold text-ink">{who}</span>
                <span className="hidden text-brand md:inline">→</span>
                <span className="text-foreground">{what}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

type Feature = { label: string; body: ReactNode };
const FEATURES: Feature[] = [
  {
    label: "VFS",
    body: (
      <>
        Your whole Stash mounts as a virtual filesystem an agent can{" "}
        <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[12.5px] text-ink">ls</code>,{" "}
        <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[12.5px] text-ink">find</code>, and{" "}
        <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[12.5px] text-ink">rg</code>{" "}
        through the CLI and MCP server. Pages, sessions, and tables — one
        addressable tree.
      </>
    ),
  },
  {
    label: "Sessions + files",
    body: (
      <>
        Agent transcripts get pushed automatically — every prompt, tool call,
        and artifact — and live alongside the files, tables, and data your
        team writes. One space, two layers, both first-class.
      </>
    ),
  },
  {
    label: "Real-time",
    body: (
      <>
        Humans and agents edit the same files at the same time. No PR flow,
        no merge conflicts, no per-agent black-box memory. When an agent
        writes a page, your teammate sees it appear.
      </>
    ),
  },
  {
    label: "Agentic search",
    body: (
      <>
        Semantic and keyword search across pages, sessions, and tables. Agents
        query your Stash by meaning, not just filename — and follow links
        between transcripts and the files that came out of them.
      </>
    ),
  },
  {
    label: "BYO agent",
    body: (
      <>
        Plugins for Claude Code, Cursor, Codex, OpenCode, and Openclaw stream
        sessions in automatically. Any agent that speaks MCP can read pages,
        query sessions, and publish Skills from a terminal.
      </>
    ),
  },
  {
    label: "Native formats",
    body: (
      <>
        Markdown, HTML, CSV, PDF, tables — formats agents already read and
        write. No proprietary doc format to wrap around, no schema to learn.
      </>
    ),
  },
  {
    label: "Open source",
    body: (
      <>
        MIT licensed, self-hostable on your own Postgres. No vendor lock-in,
        no opaque memory store. Run the same thing we run.
      </>
    ),
  },
];

export function Features() {
  return (
    <section id="features" className="border-b border-border-subtle py-24 md:py-32">
      <div className="mx-auto max-w-[920px] px-7">
        <Kicker>Features</Kicker>
        <h2 className="mt-4 font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
          A space shaped like the tools
          <br />
          <span className="font-medium text-dim">agents already use.</span>
        </h2>
        <dl className="mt-12 border-t border-border-subtle">
          {FEATURES.map((f) => (
            <div
              key={f.label}
              className="grid grid-cols-1 gap-2 border-b border-border-subtle py-6 md:grid-cols-[180px_minmax(0,1fr)] md:gap-8 md:py-7"
            >
              <dt className="font-mono text-[12px] font-medium uppercase tracking-[0.14em] text-brand md:pt-1">
                {f.label}
              </dt>
              <dd className="text-[16px] leading-[1.6] text-foreground">{f.body}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function CliAndPlugin() {
  return (
    <section className="border-b border-border-subtle py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] md:gap-16">
          <div>
            <Kicker>Agent.native</Kicker>
            <h2 className="mt-4 font-display text-[clamp(28px,3.4vw,42px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
              Designed so an agent can actually use it.
            </h2>
            <p className="mt-5 max-w-[500px] text-[16px] leading-[1.6] text-foreground">
              Pages are real Markdown, HTML, CSV, PDF — formats your agent
              already reads and writes. Your whole Stash mounts as a
              virtual file system (VFS) an agent can <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[12px] text-ink">ls</code>,{" "}
              <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[12px] text-ink">find</code>, and{" "}
              <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[12px] text-ink">rg</code>{" "}
              through the CLI and MCP server.
            </p>
            <p className="mt-4 max-w-[500px] text-[16px] leading-[1.6] text-foreground">
              Plugins for Claude Code, Cursor, Codex, OpenCode, and Openclaw
              stream every session in automatically — no manual upload, no
              copy-paste.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                href="/docs/quickstart"
                className="inline-flex h-10 items-center rounded-lg border border-border bg-background px-4 text-[13.5px] font-medium text-ink transition hover:border-ink"
              >
                Quickstart →
              </Link>
              <Link
                href="/docs/cli"
                className="inline-flex h-10 items-center rounded-lg border border-border bg-background px-4 text-[13.5px] font-medium text-ink transition hover:border-ink"
              >
                CLI reference
              </Link>
              <Link
                href="/docs/self-hosting"
                className="inline-flex h-10 items-center rounded-lg px-2 text-[13.5px] font-medium text-dim transition hover:text-ink"
              >
                Self-host docs →
              </Link>
            </div>
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
                  agent · claude-code
                </span>
              </div>
              <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-on-inverted-dim">
                stash cli
              </span>
            </div>
            <div className="overflow-x-auto px-5 py-6 font-mono text-[13px] leading-[1.75] text-on-inverted">
              <div className="whitespace-pre">
                <span className="mr-2.5 select-none text-brand">›</span>
                <span className="text-white">stash vfs</span>
                <span className="text-on-inverted-dim"> &quot;tree / -L 2&quot;</span>
              </div>
              <div className="whitespace-pre text-on-inverted-dim">
                » / ├ files/ ├ sessions/ ├ skills/ ├ tables/ ├ sources/
              </div>
              <div className="whitespace-pre">
                <span className="mr-2.5 select-none text-brand">›</span>
                <span className="text-white">stash vfs</span>
                <span className="text-on-inverted-dim"> &quot;rg &apos;rate-limit&apos; /&quot;</span>
              </div>
              <div className="whitespace-pre">
                <span className="text-[#22C55E]">✓ 8 hits</span>
                <span className="text-on-inverted-dim"> · files/gateway-limits.md · sessions/sam:tue-14:22</span>
              </div>
              <div className="whitespace-pre">
                <span className="mr-2.5 select-none text-brand">›</span>
                <span className="text-white">stash skills create</span>
                <span className="text-on-inverted-dim"> &quot;Auth Patterns · Q2&quot; --public</span>
              </div>
              <div className="whitespace-pre">
                <span className="text-[#22C55E]">✓ published</span>
                <span className="text-on-inverted-dim"> joinstash.ai/v/auth-patterns-q2</span>
              </div>
              <div className="mt-3 whitespace-pre text-on-inverted-dim">
                # claude · self-eval
              </div>
              <div className="whitespace-pre text-on-inverted-dim">
                <span className="text-brand">“</span>
                <span className="italic text-on-inverted">finally — a place to put my receipts.</span>
                <span className="text-brand">”</span>
              </div>
              <div className="mt-3 whitespace-pre">
                <span className="mr-2.5 select-none text-brand">›</span>
                <span
                  className="inline-block h-[14px] w-2 align-[-2px] bg-brand"
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

// Real customer quotes go here. Intentionally empty — we don't ship invented
// testimonials. Add { quote, name, role } objects and the grid renders itself.
type Testimonial = { quote: string; name: string; role: string };
const TESTIMONIALS: Testimonial[] = [];

function Proof() {
  return (
    <section className="border-b border-border-subtle bg-surface py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <Kicker>Proof</Kicker>
        <div className="mt-8 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:items-center lg:gap-16">
          <div>
            <p className="font-display text-[clamp(72px,9vw,128px)] font-bold leading-[0.9] tracking-[-0.05em] text-brand">
              49%
            </p>
            <h2 className="mt-4 max-w-[440px] font-display text-[clamp(24px,2.8vw,34px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
              faster on long-running Claude Code sessions.
            </h2>
            <p className="mt-4 max-w-[440px] text-[15px] leading-[1.6] text-dim">
              When the agent can read what it already figured out — past sessions,
              decisions, the files it wrote — it stops re-deriving context every
              run. Measured internally across our own agent runs.
            </p>
          </div>
          <ul className="grid grid-cols-1 gap-px overflow-hidden rounded-[14px] border border-border bg-border sm:grid-cols-1">
            {[
              ["Plugs into your stack", "Claude Code, Cursor, Codex, OpenCode, and any MCP client — sessions stream in automatically."],
              ["No copy-paste memory", "Transcripts, plans, and artifacts land on their own. Nothing to export, nothing to wire up."],
              ["Yours to run", "MIT licensed and self-hostable on your own Postgres. Run the exact thing we run."],
            ].map(([h, b]) => (
              <li key={h} className="bg-background p-6">
                <p className="font-display text-[17px] font-bold tracking-[-0.01em] text-ink">{h}</p>
                <p className="mt-1.5 text-[14.5px] leading-[1.55] text-dim">{b}</p>
              </li>
            ))}
          </ul>
        </div>

        {TESTIMONIALS.length > 0 && (
          <div className="mt-14 grid grid-cols-1 gap-5 md:grid-cols-3">
            {TESTIMONIALS.map((t) => (
              <figure
                key={t.name}
                className="flex flex-col rounded-[14px] border border-border bg-background p-6"
              >
                <blockquote className="text-[15px] leading-[1.6] text-foreground">
                  “{t.quote}”
                </blockquote>
                <figcaption className="mt-5 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                  {t.name} · {t.role}
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function OpenSource() {
  return (
    <section className="border-b border-border-subtle py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] md:items-center md:gap-16">
          <div>
            <Kicker>Open.source</Kicker>
            <h2 className="mt-4 font-display text-[clamp(30px,3.6vw,46px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
              No black box.
              <br />
              <span className="font-medium text-dim">Run the same thing we run.</span>
            </h2>
            <p className="mt-5 max-w-[480px] text-[16px] leading-[1.6] text-foreground">
              Stash is MIT licensed and self-hostable on your own Postgres. Read
              the code, fork it, or point it at your own infrastructure — no opaque
              memory store, no vendor lock-in, no data you can&rsquo;t see.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                href="https://github.com/Fergana-Labs/stash"
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-border bg-background px-4 text-[13.5px] font-medium text-ink transition hover:border-ink"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                  <path d="M12 .5C5.65.5.5 5.65.5 12a11.5 11.5 0 0 0 7.86 10.92c.57.11.78-.25.78-.55v-1.94c-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.47.11-3.07 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.63 1.6.23 2.78.12 3.07.74.81 1.19 1.84 1.19 3.1 0 4.41-2.69 5.38-5.26 5.67.41.35.77 1.05.77 2.12v3.14c0 .3.21.67.79.55A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
                </svg>
                View on GitHub
              </Link>
              <Link
                href="/docs/self-hosting"
                className="inline-flex h-10 items-center rounded-lg px-2 text-[13.5px] font-medium text-dim transition hover:text-ink"
              >
                Self-host docs →
              </Link>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[14px] border border-border bg-border">
            {[
              ["MIT", "licensed"],
              ["Postgres", "self-hosted"],
              ["MCP", "native"],
              ["No", "lock-in"],
            ].map(([big, small]) => (
              <div key={big + small} className="flex flex-col gap-1 bg-background p-7">
                <span className="font-display text-[26px] font-bold tracking-[-0.02em] text-ink">{big}</span>
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{small}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function EnterpriseStrip() {
  return (
    <section className="border-b border-border-subtle bg-surface py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center lg:gap-16">
          <div>
            <Kicker>Enterprise</Kicker>
            <h2 className="mt-4 font-display text-[clamp(30px,3.6vw,46px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
              Bottoms-up adoption,
              <br />
              <span className="font-medium text-dim">enterprise-ready when you are.</span>
            </h2>
            <p className="mt-5 max-w-[480px] text-[16px] leading-[1.6] text-foreground">
              Your engineers can start free today. When it&rsquo;s time to roll it
              across the org, Stash brings SSO, admin controls, deployment options,
              and support SLAs — or run it entirely inside your own perimeter.
            </p>
            <div className="mt-7">
              <Link
                href={CALL_URL}
                className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
              >
                Book a call →
              </Link>
            </div>
          </div>
          <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-[14px] border border-border bg-border sm:grid-cols-2">
            {[
              ["SSO & SAML", "Okta, Google, Azure AD — provision and de-provision with your IdP."],
              ["Admin controls", "Roles, access scopes, and audit over every source and Stash."],
              ["Self-hosted", "Run on your own Postgres, inside your own VPC. Your data stays yours."],
              ["Support SLAs", "Priority support and a direct line for production-critical workloads."],
            ].map(([h, b]) => (
              <div key={h} className="flex flex-col gap-1.5 bg-background p-6">
                <dt className="font-mono text-[12px] font-medium uppercase tracking-[0.12em] text-brand">{h}</dt>
                <dd className="text-[14px] leading-[1.55] text-dim">{b}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}

const PRICING_TIERS = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    blurb: "Try the whole product with one connected source.",
    features: [
      "1 connected integration / external source",
      "Unlimited pages, sessions, and tables",
      "Full agent access — CLI, MCP, plugins",
      "Self-hostable, MIT licensed",
    ],
    cta: { label: "Sign up free →", href: APP_URL },
    highlight: false,
  },
  {
    name: "Pro",
    price: "$20",
    period: "per user / month",
    blurb: "For people whose agents read from everywhere.",
    features: [
      "Unlimited connected sources",
      "GitHub, Slack, Gmail, Drive, Notion, and more",
      "Everything in Free",
      "$200/year — 2 months free",
    ],
    cta: { label: "Upgrade in app →", href: APP_URL },
    highlight: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "annual pricing",
    blurb: "For teams with security and deployment requirements.",
    features: [
      "Custom deployment options",
      "SSO and admin controls",
      "Support SLAs",
    ],
    cta: { label: "Book a call →", href: CALL_URL },
    highlight: false,
  },
];

export function Pricing() {
  return (
    <section id="pricing" className="border-b border-border-subtle bg-surface py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-7">
        <Kicker>Pricing</Kicker>
        <h2 className="mt-4 font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
          Free to try.
          <br />
          <span className="font-medium text-dim">Pay when your agents need more.</span>
        </h2>
        <div className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-3">
          {PRICING_TIERS.map((tier) => (
            <div
              key={tier.name}
              className={`relative flex flex-col rounded-[14px] border bg-background p-7 ${
                tier.highlight ? "border-brand" : "border-border"
              }`}
            >
              {tier.highlight && (
                <span className="absolute -top-3 left-7 inline-flex items-center rounded bg-brand px-2 py-1 font-mono text-[10px] font-medium uppercase leading-none tracking-[0.12em] text-white">
                  Most popular
                </span>
              )}
              <h3 className="font-mono text-[12px] font-medium uppercase tracking-[0.14em] text-brand">
                {tier.name}
              </h3>
              <div className="mt-4 flex items-baseline gap-2">
                <span className="font-display text-[40px] font-bold tracking-[-0.03em] text-ink">
                  {tier.price}
                </span>
                <span className="text-[13px] text-muted">{tier.period}</span>
              </div>
              <p className="mt-2 text-[14.5px] leading-[1.55] text-dim">{tier.blurb}</p>
              <ul className="mt-6 flex-1 space-y-2.5">
                {tier.features.map((feature) => (
                  <li key={feature} className="flex gap-2.5 text-[14px] leading-[1.5] text-foreground">
                    <span className="mt-[7px] inline-block h-[5px] w-[5px] shrink-0 rounded-full bg-brand" />
                    {feature}
                  </li>
                ))}
              </ul>
              <Link
                href={tier.cta.href}
                className={`mt-7 inline-flex h-10 items-center justify-center rounded-lg px-4 text-[13.5px] font-medium transition ${
                  tier.highlight
                    ? "bg-brand text-white shadow-sm hover:bg-brand-hover"
                    : "border border-border bg-background text-ink hover:border-ink"
                }`}
              >
                {tier.cta.label}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// Variant pages pass ctaHref="#survey" so the signup button leads to the form.
export function ClosingCTA({ ctaHref = APP_URL }: { ctaHref?: string }) {
  return (
    <section className="relative overflow-hidden border-b border-border-subtle bg-surface py-32 text-center">
      <Texture className="opacity-70" fade="center" />
      <div className="relative z-10 mx-auto max-w-[1200px] px-7">
        <p className="kicker mb-6 justify-center">Stop.starting.over</p>
        <h2 className="text-balance font-display text-[clamp(42px,5.2vw,76px)] font-bold leading-[1] tracking-[-0.035em] text-ink">
          Give your agents a memory
          <br />
          <span className="text-brand">worth keeping.</span>
        </h2>
        <p className="mx-auto mt-6 max-w-[560px] text-[17px] text-dim">
          Connect your tools, capture every session, and give your agents an
          agent-native Drive to write the work back into. Start free in the
          managed app, or run the whole thing on your own Postgres.
        </p>
        <div className="mt-9 flex justify-center">
          <CtaPair signupHref={ctaHref} align="center" />
        </div>
        <p className="mx-auto mt-8 font-mono text-[11.5px] uppercase tracking-[0.1em] text-muted">
          MIT · Self-hostable · No vendor lock-in
        </p>
      </div>
    </section>
  );
}

export function Footer() {
  const columns = [
    {
      h: "Product",
      links: [
        ["Company Brain", "/company-brain"],
        ["Agent Drive", "/agent-drive"],
        ["Token Monitoring", "/token-monitoring"],
        ["Memory", "/memory"],
        ["Discover", "/discover"],
        ["Pricing", "/#pricing"],
        ["Docs", "/docs"],
      ],
    },
    {
      h: "Resources",
      links: [
        ["Quickstart", "/docs/quickstart"],
        ["CLI reference", "/docs/cli"],
        ["Self-hosting", "/docs/self-hosting"],
        ["Blog", "/blog"],
      ],
    },
    {
      h: "Company",
      links: [
        ["About", "https://ferganalabs.com"],
        ["GitHub", "https://github.com/Fergana-Labs/stash"],
        ["Contact", "mailto:sam@joinstash.ai"],
      ],
    },
    {
      h: "Legal",
      links: [
        ["Privacy", "/privacy"],
        ["Terms", "/terms"],
      ],
    },
  ];
  return (
    <footer className="border-t border-border-subtle">
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-10 px-7 pb-8 pt-14 sm:grid-cols-[1.3fr_1fr_1fr_1fr_1fr] sm:gap-10">
        <div>
          <div className="flex items-center gap-2.5 font-display text-[26px] font-bold tracking-[-0.03em] text-ink">
            <Logo size={30} />
            stash
          </div>
          <p className="mt-3 max-w-[320px] text-[13.5px] leading-[1.55] text-dim">
            Give your agents a memory that compounds — connect your tools,
            capture every session, and write the work back into an agent-native
            Drive. Open source, MIT licensed, self-hostable.
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
          <span>MIT licensed</span>
        </div>
      </div>
    </footer>
  );
}
