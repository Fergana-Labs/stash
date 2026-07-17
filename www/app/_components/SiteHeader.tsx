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
          className="flex items-center gap-2.5 font-display text-[20px] font-bold tracking-[-0.03em] text-ink"
        >
          <Logo size={28} />
          stash
        </Link>
        <nav className="flex items-center gap-2 text-[14px] text-dim">
          <UseCasesMenu />
          <NavLink href="/docs">Docs</NavLink>
          <NavLink href="/blog">Blog</NavLink>
          <NavLink href="/contact-sales">Book a call</NavLink>
          <Link
            href="/login"
            className="hidden h-10 items-center rounded-lg px-3 text-[14px] font-medium text-ink transition hover:bg-raised sm:inline-flex"
          >
            Sign in
          </Link>
          {ctaHref.startsWith("#") ? (
            <ScrollLink to={ctaHref} className={ctaClassName}>
              Sign up free
            </ScrollLink>
          ) : (
            <Link href={ctaHref} className={ctaClassName}>
              Sign up free
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}

function NavLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink"
    >
      {children}
    </Link>
  );
}

const USE_CASES = [
  ["Company Brain", "/company-brain", "All your tools as one agent-native source of truth"],
  ["Memory & Observability", "/memory", "Retrieval that doesn't miss, plus every agent session"],
  ["For SMBs", "/smb", "Find the hours AI can give back"],
];

// CSS-only dropdown (no client JS): opens on hover and on keyboard focus of
// any child via group-focus-within. Collapses below lg so the nav stays tidy.
function UseCasesMenu() {
  return (
    <div className="group relative hidden lg:block">
      <button
        type="button"
        className="inline-flex items-center gap-1 rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink group-hover:bg-raised group-hover:text-ink"
      >
        Use-cases
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
          className="mt-px transition-transform group-hover:rotate-180"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <div className="invisible absolute left-0 top-full z-50 pt-2 opacity-0 transition group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100">
        <div className="w-64 rounded-xl border border-border bg-background p-1.5 shadow-[var(--shadow-card)]">
          {USE_CASES.map(([name, href, blurb]) => (
            <Link
              key={href}
              href={href}
              className="block rounded-lg px-3 py-2 transition hover:bg-raised"
            >
              <span className="block text-[14px] font-medium text-ink">{name}</span>
              <span className="mt-0.5 block text-[12.5px] leading-snug text-dim">{blurb}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
