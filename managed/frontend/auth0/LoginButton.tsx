"use client";

export default function LoginButton({ cliSession }: { cliSession?: string | null }) {
  const returnTo = cliSession ? `/login?cli=${encodeURIComponent(cliSession)}` : "/login";
  const href = `/auth/login?returnTo=${encodeURIComponent(returnTo)}`;
  return (
    <a
      href={href}
      className="block w-full bg-surface-hover hover:bg-border text-foreground py-2.5 rounded-xl text-sm font-medium text-center transition-colors"
    >
      Sign in with Auth0
    </a>
  );
}
