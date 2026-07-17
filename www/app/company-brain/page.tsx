import type { Metadata } from "next";
import Link from "next/link";

import { INTEGRATIONS, integrationIcon } from "../_components/BrandIcons";
import CtaPair from "../_components/CtaPair";
import SiteHeader from "../_components/SiteHeader";
import Texture from "../_components/Texture";

export const metadata: Metadata = {
  title: "Company Brain · Stash",
  description:
    "All your company's context in one place every agent can read. Stash connects your tools into a permission-aware source of truth, mounted as an agent-native Drive — Markdown, HTML, and Skills your agents ls, find, and rg.",
};

const DRIVE_FEATURES = [
  [
    "Markdown & HTML, natively",
    "Pages are real Markdown and HTML, plus CSV, PDF, and images. The formats your agent already reads and writes, not a proprietary block format.",
  ],
  [
    "A virtual filesystem",
    "The whole Drive mounts as a filesystem your agent can ls, find, and rg. Pages, files, Skills, and session transcripts sit side by side, addressed by path.",
  ],
  [
    "Skills are just folders",
    "A Skill is a folder with a SKILL.md and the pages, files, and sessions it needs. No new format to learn; your agent reads it like a repo.",
  ],
  [
    "WYSIWYG HTML editing",
    "When your agent builds an HTML page, a report, a dashboard, or a deck, you edit it visually in a WYSIWYG editor. Adjust the result by hand without touching the markup.",
  ],
  [
    "Real-time collaboration",
    "You and your agent edit the same page at the same time, two cursors at once. Edits save automatically.",
  ],
  [
    "Reachable everywhere",
    "Through the CLI, the Stash MCP server, or the HTTP API. Point Claude Code, Cursor, Codex, or OpenCode at it and they read and write directly.",
  ],
  [
    "Sessions land here too",
    "Every coding-agent session streams in automatically, indexed alongside your docs. No manual upload, no copy-paste.",
  ],
];

export default function CompanyBrainPage() {
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
          <p className="kicker rise-in mb-6">Company.brain</p>
          <h1 className="max-w-[920px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-ink">
            Your company&apos;s context, in one place{" "}
            <span className="text-brand">every agent can read.</span>
          </h1>
          <p className="mt-7 max-w-[620px] text-[18px] leading-[1.55] text-foreground">
            Your agent doesn&apos;t know your people, your projects, or what
            shipped yesterday. Stash connects every tool your company uses into
            one permission-aware source of truth, exposed as a filesystem any
            agent can read. Set up in minutes, scoped to exactly what you grant.
          </p>
          <div className="mt-9">
            <CtaPair />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Connect once. Your agent reads it all.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {INTEGRATIONS.map((it) => (
              <div
                key={it.provider}
                className="rounded-[12px] border border-border bg-background p-5 transition-colors hover:border-brand"
              >
                <div className="flex items-center gap-2.5">
                  <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center">
                    {integrationIcon(it.provider, 24)}
                  </span>
                  <div className="font-display text-[17px] font-bold tracking-[-0.01em] text-ink">
                    {it.name}
                  </div>
                </div>
                <p className="mt-2 text-[14px] leading-[1.55] text-dim">{it.blurb}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="kicker">Agent.drive</p>
          <h2 className="mt-5 max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            A Drive that speaks your agent&apos;s language.
          </h2>
          <p className="mt-5 max-w-[640px] text-[16px] leading-[1.6] text-foreground">
            Your brain isn&apos;t just readable — it&apos;s a place agents work.
            Pages are real Markdown and HTML, mounted as a virtual filesystem
            your agent can ls, find, and rg, the same way it works in a repo.
            Package repeatable processes as Skills — folders with a SKILL.md —
            and share them with a link.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {DRIVE_FEATURES.map(([name, blurb]) => (
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
          <div className="mt-10 flex flex-wrap gap-3">
            <Link
              href="/discover"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Browse Discover →
            </Link>
            <Link
              href="/pages"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Share a doc →
            </Link>
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-8 px-7 md:grid-cols-3 md:gap-12">
          <Point title="Connect">
            OAuth in and permissions are inherited automatically. No tokens to
            paste, no scripts to run, and access stays scoped to exactly what you
            grant.
          </Point>
          <Point title="Synthesize">
            Stash continuously maps your sources into a context graph of the
            company: the people, projects, and decisions, and how they connect.
            Kept accurate in real time, not exported once and left to go stale.
          </Point>
          <Point title="Serve">
            Ask one question and your agent answers across every source at once,
            as structured results or LLM-ready Markdown, with citations back to
            the source.
          </Point>
        </div>
      </section>

      <section className="relative overflow-hidden py-28 text-center">
        <Texture className="opacity-70" fade="center" />
        <div className="relative z-10 mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-bold leading-[1.0] tracking-[-0.035em] text-ink">
            Give your agents the why, not just the what.
          </h2>
          <div className="mt-8 flex justify-center">
            <CtaPair align="center" />
          </div>
          <Link
            href="/memory"
            className="mt-6 inline-flex font-mono text-[13px] text-dim transition hover:text-brand"
          >
            See Memory & Observability →
          </Link>
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
