"use client";

export default function LoginButton({ cliSession }: { cliSession?: string | null }) {
  const returnTo = cliSession ? `/login?cli=${encodeURIComponent(cliSession)}` : "/login";
  const href = `/auth/login?returnTo=${encodeURIComponent(returnTo)}`;
  return (
    <div className="space-y-4">
      <p className="text-sm text-dim text-center">
        You&apos;ll be redirected to a secure sign-in page.
      </p>
      <a
        href={href}
        className="group flex items-center justify-center gap-2 w-full bg-brand hover:bg-brand-hover text-white py-2.5 rounded-xl text-sm font-semibold text-center transition-all shadow-[0_8px_24px_-8px_oklch(0.7_0.14_55_/_0.5)] hover:shadow-[0_10px_28px_-6px_oklch(0.7_0.14_55_/_0.6)]"
      >
        Continue to sign in
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5">
          <path d="M5 12h14M13 5l7 7-7 7" />
        </svg>
      </a>
      <p className="flex items-center justify-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.14em] text-muted">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <rect x="4" y="11" width="16" height="10" rx="2" />
          <path d="M8 11V7a4 4 0 0 1 8 0v4" />
        </svg>
        Secured by Auth0
      </p>
    </div>
  );
}
