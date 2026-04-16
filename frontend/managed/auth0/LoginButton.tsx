"use client";

export default function LoginButton({ cliSession }: { cliSession?: string | null }) {
  const returnTo = cliSession ? `/login?cli=${encodeURIComponent(cliSession)}` : "/login";
  const href = `/auth/login?returnTo=${encodeURIComponent(returnTo)}`;
  return (
    <a
      href={href}
      className="group flex items-center justify-center gap-2 w-full bg-brand hover:bg-brand-hover text-white py-2.5 rounded-xl text-sm font-semibold text-center transition-all shadow-[0_8px_24px_-8px_oklch(0.7_0.14_55_/_0.5)] hover:shadow-[0_10px_28px_-6px_oklch(0.7_0.14_55_/_0.6)]"
    >
      Continue with Auth0
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5">
        <path d="M5 12h14M13 5l7 7-7 7" />
      </svg>
    </a>
  );
}
