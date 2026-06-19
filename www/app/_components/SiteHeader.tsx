import Link from "next/link";

import Logo from "./Logo";
import ScrollLink from "./ScrollLink";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

// Shared top nav for the landing page and the use-case pages, so the two
// primary use-case links stay identical everywhere they appear. The
// message-test pages pass ctaHref="#survey" so signup leads to their form.
export default function SiteHeader({ ctaHref = APP_URL }: { ctaHref?: string }) {
  const ctaClassName =
    "hidden h-10 items-center rounded-lg bg-brand px-[18px] text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover sm:inline-flex";
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
          <div className="group relative hidden sm:block">
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-md px-3 py-2 transition group-hover:bg-raised group-hover:text-ink"
            >
              Use cases
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            <div className="invisible absolute left-0 top-full w-60 pt-2 opacity-0 transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
              <div className="overflow-hidden rounded-xl border border-border bg-background p-1.5 shadow-card">
                <UseCaseItem href="/connect-your-data" title="Connect your data" desc="Plug in GitHub, Drive, Gmail, Notion, Slack." />
                <UseCaseItem href="/agent-native-drive" title="Agent-native Drive" desc="A workspace agents read and write like a repo." />
                <UseCaseItem href="/memory" title="Memory" desc="Best-in-class retrieval: wiki + vectors + grep." />
                <UseCaseItem href="/audit-agent-sessions" title="Audit agent sessions" desc="Onboard, coach, and monitor like Granola or Gong." />
                <UseCaseItem href="/skills" title="Skills" desc="Bundle repeatable processes, share them, fork them." />
              </div>
            </div>
          </div>
          <Link
            href="/docs"
            className="rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink"
          >
            Docs
          </Link>
          <Link
            href="/blog"
            className="rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink"
          >
            Blog
          </Link>
          <Link
            href="/login"
            className="hidden h-10 items-center rounded-lg border border-border bg-background px-[18px] text-[14px] font-medium text-ink transition hover:border-ink sm:inline-flex"
          >
            Sign in
          </Link>
          {ctaHref.startsWith("#") ? (
            <ScrollLink to={ctaHref} className={ctaClassName}>
              Start free
            </ScrollLink>
          ) : (
            <Link href={ctaHref} className={ctaClassName}>
              Start free
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}

function UseCaseItem({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link
      href={href}
      className="block rounded-lg px-3 py-2 transition hover:bg-raised"
    >
      <span className="block text-[14px] font-medium text-ink">{title}</span>
      <span className="mt-0.5 block text-[12.5px] leading-snug text-dim">{desc}</span>
    </Link>
  );
}
