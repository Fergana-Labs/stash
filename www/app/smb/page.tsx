import type { Metadata } from "next";

import ScrollLink from "../_components/ScrollLink";
import SiteHeader from "../_components/SiteHeader";
import Texture from "../_components/Texture";
import AssessmentChat from "./AssessmentChat";

export const metadata: Metadata = {
  title: "Stash for SMBs · Free AI Snapshot",
  description:
    "Three minutes of questions, one page of answers: where your hours are going, the one tool to start with, and what those hours are worth — from your own numbers.",
};

const PAINS = [
  {
    title: "Knowledge is everywhere",
    body: "Client info in Google Drive, pricing in a spreadsheet, history in email threads — and the rest in your head.",
  },
  {
    title: "You keep re-explaining",
    body: "Every new tool, contractor, and hire gets the same walkthrough of how your business works. Again.",
  },
  {
    title: "ChatGPT doesn't know you",
    body: "You've tried AI, but it writes like a stranger — because it's never seen your clients, your voice, or your work.",
  },
  {
    title: "Follow-ups slip",
    body: "Proposals, promises, and open loops live in your head. Some of them don't make it out.",
  },
  {
    title: "Decisions get forgotten",
    body: "Why did we pick that vendor? Nobody remembers. So it gets debated, decided, and forgotten all over again.",
  },
  {
    title: "You don't know where to start",
    body: "You know AI could help. The 400 tools screaming for attention don't make it any clearer.",
  },
];

export default function SmbPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader ctaHref="#snapshot" />

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
          <h1 className="max-w-[920px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-ink">
            Find out where your business is{" "}
            <span className="text-brand">leaving hours on the table.</span>
          </h1>
          <p className="mt-7 max-w-[560px] text-[18px] leading-[1.55] text-foreground">
            We can help you figure out the best way to organize all your
            information so that you can automate the repetitive work and get
            time back.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <ScrollLink
              to="#snapshot"
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Get my free snapshot →
            </ScrollLink>
            <a
              href="https://calendly.com/sam-ferganalabs/30min"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
            >
              Book a call
            </a>
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="max-w-[720px] font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Common problems we see our customers facing
          </h2>
          <p className="mt-4 max-w-[560px] text-[16px] leading-[1.6] text-dim">
            If two or more of these hit home, the snapshot will find you hours.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {PAINS.map((p) => (
              <div
                key={p.title}
                className="rounded-[12px] border border-border bg-background p-6 transition-colors hover:border-brand"
              >
                <h3 className="font-display text-[17px] font-bold tracking-[-0.01em] text-ink">
                  {p.title}
                </h3>
                <p className="mt-2 text-[14.5px] leading-[1.55] text-dim">{p.body}</p>
              </div>
            ))}
          </div>
          <div className="mt-8 text-center">
            <ScrollLink
              to="#snapshot"
              className="text-[15px] font-medium text-brand transition hover:text-brand-hover"
            >
              That&apos;s us — show me the snapshot →
            </ScrollLink>
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <div className="mx-auto aspect-video max-w-[860px] overflow-hidden rounded-[14px] border border-border shadow-[var(--shadow-terminal)]">
            <iframe
              className="h-full w-full"
              src="https://www.youtube-nocookie.com/embed/GPYzqp2gctU"
              title="Stash for small and medium businesses"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        </div>
      </section>

      <section id="snapshot" className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="max-w-[760px] font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Answer a few questions. Walk away with{" "}
            <span className="text-brand">the report.</span>
          </h2>
          <div className="mt-10 max-w-[760px]">
            <AssessmentChat />
          </div>
        </div>
      </section>

      <section className="relative overflow-hidden py-28 text-center">
        <Texture className="opacity-70" fade="center" />
        <div className="relative z-10 mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-bold leading-[1.0] tracking-[-0.035em] text-ink">
            We find the hours.{" "}
            <span className="text-brand">Then we build the system that keeps them.</span>
          </h2>
          <p className="mx-auto mt-5 max-w-[520px] text-[16px] leading-[1.6] text-dim">
            The snapshot shows where your business is leaving hours on the
            table. The full engagement goes further: a complete audit, then one
            organized system for everything your business knows — that you own.
          </p>
          <div className="mt-8 flex justify-center">
            <ScrollLink
              to="#snapshot"
              className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
            >
              Get my free snapshot →
            </ScrollLink>
          </div>
        </div>
      </section>
    </main>
  );
}
