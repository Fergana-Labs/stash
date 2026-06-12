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
          <Link
            href="/connect-your-data"
            className="hidden rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink sm:inline-flex"
          >
            Connect your data
          </Link>
          <Link
            href="/agent-native-drive"
            className="hidden rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink sm:inline-flex"
          >
            Agent-native Drive
          </Link>
          <Link
            href="/#pricing"
            className="hidden rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink sm:inline-flex"
          >
            Pricing
          </Link>
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
            href="/contact-sales"
            className="rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink"
          >
            Contact sales
          </Link>
          <Link
            href="https://github.com/Fergana-Labs/stash"
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink"
            aria-label="Stash on GitHub"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M12 .5C5.65.5.5 5.65.5 12a11.5 11.5 0 0 0 7.86 10.92c.57.11.78-.25.78-.55v-1.94c-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.47.11-3.07 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.63 1.6.23 2.78.12 3.07.74.81 1.19 1.84 1.19 3.1 0 4.41-2.69 5.38-5.26 5.67.41.35.77 1.05.77 2.12v3.14c0 .3.21.67.79.55A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
            </svg>
            <span className="hidden sm:inline">GitHub</span>
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
