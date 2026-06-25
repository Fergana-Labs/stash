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
          <NavLink href="/company-brain" useCase>Company Brain</NavLink>
          <NavLink href="/agent-drive" useCase>Agent Drive</NavLink>
          <NavLink href="/token-monitoring" useCase>Token Monitoring</NavLink>
          <NavLink href="/memory" useCase>Memory</NavLink>
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

// Use-case links collapse below the lg breakpoint so the nav doesn't crowd;
// Docs and Blog stay visible everywhere.
function NavLink({
  href,
  useCase = false,
  children,
}: {
  href: string;
  useCase?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`${useCase ? "hidden lg:inline-flex" : ""} rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink`}
    >
      {children}
    </Link>
  );
}
