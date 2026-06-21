import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../_components/SiteHeader";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export const metadata: Metadata = {
  title: "Skills · Stash",
  description:
    "Package any repeatable process into a Skill — a folder of pages, files, prompts, and sessions your agents can run. Share it with a link, fork it, and keep it in sync.",
};

const FEATURES = [
  [
    "A Skill is a folder",
    "Just a folder with a SKILL.md and the pages, files, and sessions it needs. No proprietary format — your agent reads it like a repo.",
  ],
  [
    "Bundle a repeatable process",
    "Capture how a task actually gets done — the steps, the context, the examples — into one Skill your team and their agents can run again.",
  ],
  [
    "Share with a link",
    "Publish a Skill public on Discover or share it privately with specific people. They bring their own agents and run the same process.",
  ],
  [
    "Fork and stay in sync",
    "Anyone can fork a Skill into their own Stash, and it stays live with the source as it changes — improvements flow downstream.",
  ],
  [
    "Run it anywhere",
    "Skills are reachable through the CLI, the Stash MCP server, and the API. Point Claude Code, Cursor, Codex, or OpenCode at one and it loads the process.",
  ],
  [
    "Compounds over time",
    "Promote your best sessions and docs into Skills, so a process you figure out once becomes something the whole team repeats.",
  ],
];

export default function SkillsPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="border-b border-border-subtle py-24 md:py-32">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Skills
          </p>
          <h1 className="mt-5 max-w-[900px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-black leading-[1.02] tracking-[-0.04em] text-ink">
            Package any repeatable process into a{" "}
            <span className="text-brand">Skill.</span>
          </h1>
          <p className="mt-7 max-w-[620px] text-[18px] leading-[1.55] text-foreground">
            A Skill bundles the pages, files, prompts, and sessions behind a
            workflow into one folder your agents can run. Share it with a link,
            fork it into your own Stash, and keep it in sync — so a process
            you figure out once becomes something your whole team repeats.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href={APP_URL}
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Start free →
            </Link>
            <Link
              href="/discover"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Browse Discover →
            </Link>
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Repeatable processes, packaged and shared.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(([name, blurb]) => (
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

      <section className="border-b border-border-subtle py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Discover
          </p>
          <h2 className="mt-5 max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Public Skills from teams building in the open.
          </h2>
          <p className="mt-5 max-w-[620px] text-[16px] leading-[1.6] text-foreground">
            Discover is where published Skills live. Browse sessions, pages,
            tables, and files from public Skills, open one to read it without
            signing in, and fork the ones you want into your own Stash.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-8 md:grid-cols-3 md:gap-12">
            <Point title="Publish in one step">
              Turn any folder into a public Skill with a link. It shows up on
              Discover for anyone to find, read, and fork.
            </Point>
            <Point title="Browse what others ship">
              See how other teams package their workflows, and read the real
              sessions and docs behind them — no signup to look.
            </Point>
            <Point title="Fork into your Stash">
              Pull a Skill into your own Stash and run it with your agents. It
              stays live with the source as the author improves it.
            </Point>
          </div>
          <div className="mt-10">
            <Link
              href="/discover"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Browse Discover →
            </Link>
          </div>
        </div>
      </section>

      <section className="bg-surface py-28 text-center">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-black leading-[1.0] tracking-[-0.04em] text-ink">
            Build a process once. Share it everywhere.
          </h2>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href={APP_URL}
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Start free →
            </Link>
            <Link
              href="/agent-native-drive"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Agent-native Drive →
            </Link>
          </div>
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
