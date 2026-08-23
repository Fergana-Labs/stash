import Link from "next/link";

import Logo from "./Logo";
import ScrollLink from "./ScrollLink";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";
// Signup must land on the auth flow — the app root is the public feed and
// shows a signed-out visitor no way to create an account.
const SIGNUP_URL = `${APP_URL}/login?mode=register`;
const GITHUB_URL = "https://github.com/Fergana-Labs/stash";

const NAV = [
  ["Internal agents", "/internal-agents"],
  ["External agents", "/external-agents"],
  ["Pricing", "/pricing"],
  ["Blog", "/blog"],
  ["GitHub", GITHUB_URL],
];

// One header everywhere. `wide` drops the max width for the docs shell, which
// runs full-bleed with its own sidebar.
export default function SiteHeader({
  current,
  wide = false,
  ctaHref = SIGNUP_URL,
}: {
  current?: string;
  wide?: boolean;
  /** The message-test pages point signup at their own on-page form. */
  ctaHref?: string;
}) {
  const ctaClass =
    "inline-flex h-[38px] items-center rounded-lg bg-brand px-[15px] text-[14px] font-medium text-white transition hover:bg-brand-hover";
  return (
    <header className="sticky top-0 z-50 border-b border-border-subtle bg-background/90 backdrop-blur">
      <div
        className={`flex h-16 items-center gap-6 px-5 sm:px-7 ${
          wide ? "" : "mx-auto max-w-[1180px]"
        }`}
      >
        <Link
          href="/"
          className="flex items-center gap-2.5 font-display text-[19px] font-medium tracking-[-0.03em] text-ink"
        >
          <Logo size={24} />
          Stash
        </Link>

        <nav className="hidden items-center gap-6 text-[14.5px] text-dim md:flex">
          {NAV.map(([label, href]) => (
            <Link
              key={href}
              href={href}
              className={`transition hover:text-ink ${current === label ? "text-ink" : ""}`}
            >
              {label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3.5">
          <Link
            href="/contact-sales"
            className="hidden h-[38px] items-center rounded-lg border border-border px-[15px] text-[14px] font-medium text-ink transition hover:border-ink sm:inline-flex"
          >
            Book a call
          </Link>
          <Link
            href={`${APP_URL}/login`}
            className="hidden text-[14.5px] text-dim transition hover:text-ink sm:inline"
          >
            Sign in
          </Link>
          {ctaHref.startsWith("#") ? (
            <ScrollLink to={ctaHref} className={ctaClass}>
              Sign up
            </ScrollLink>
          ) : (
            <Link href={ctaHref} className={ctaClass}>
              Sign up
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
