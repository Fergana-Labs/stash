import type { Metadata } from "next";
import Link from "next/link";

import ContactSalesForm from "./ContactSalesForm";

export const metadata: Metadata = {
  title: "Contact sales · Stash",
  description:
    "Book a demo of Stash for your team. We'll show you how shared agent memory compounds across your engineers.",
};

export default function ContactSalesPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border-subtle bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-7">
          <Link
            href="/"
            className="font-display text-[20px] font-black tracking-[-0.03em] text-ink"
          >
            stash
          </Link>
          <nav className="flex items-center gap-6 text-[14px] text-dim">
            <Link href="/docs" className="transition hover:text-ink">
              Docs
            </Link>
            <Link href="/" className="transition hover:text-ink">
              Home
            </Link>
          </nav>
        </div>
      </header>

      <section className="mx-auto grid max-w-[1100px] grid-cols-1 gap-12 px-7 pb-24 pt-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-16">
        <div>
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Contact sales
          </p>
          <h1 className="mt-5 text-balance font-display text-[clamp(36px,4.6vw,56px)] font-black leading-[1.02] tracking-[-0.035em] text-ink">
            Book a demo for
            <br />
            <span className="text-brand">your team.</span>
          </h1>
          <p className="mt-6 max-w-[440px] text-[17px] leading-[1.6] text-foreground">
            Tell us a bit about your team and we&apos;ll set up a 30-minute
            walkthrough. We&apos;ll cover how Stash captures every agent run,
            curates a shared wiki, and answers questions across your team&apos;s
            history.
          </p>

          <ul className="mt-8 flex flex-col gap-3 text-[14px] text-dim">
            <li className="flex items-start gap-2.5">
              <span className="mt-[7px] h-[6px] w-[6px] shrink-0 rounded-full bg-brand" />
              30-minute live walkthrough tailored to your stack.
            </li>
            <li className="flex items-start gap-2.5">
              <span className="mt-[7px] h-[6px] w-[6px] shrink-0 rounded-full bg-brand" />
              Pricing and self-host options for security-sensitive teams.
            </li>
            <li className="flex items-start gap-2.5">
              <span className="mt-[7px] h-[6px] w-[6px] shrink-0 rounded-full bg-brand" />
              Help wiring Stash into Claude Code, Cursor, Codex, and OpenCode.
            </li>
          </ul>
        </div>

        <ContactSalesForm />
      </section>
    </main>
  );
}
