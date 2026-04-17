import Link from "next/link";
import { redirect } from "next/navigation";

import CopyButton from "./CopyButton";

export const dynamic = "force-dynamic";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://moltchat.onrender.com";
const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

// Server component. Renders the user's CLI sign-in token after Auth0 sign-in,
// for paste-back into a Claude Code session driving `stash auth ... --api-key`.
export default async function ConnectTokenPage() {
  if (!AUTH0_ENABLED) {
    return (
      <Shell>
        <Heading>Sign-in is not configured</Heading>
        <Body>
          This deployment of stash.ac doesn&apos;t have <code>NEXT_PUBLIC_AUTH0_ENABLED</code>{" "}
          turned on. Set it on the Vercel project (along with the standard{" "}
          <code>AUTH0_*</code> env vars) and redeploy.
        </Body>
      </Shell>
    );
  }

  const { auth0 } = await import("@managed/auth0/client");
  const session = await auth0.getSession();
  if (!session) {
    redirect("/auth/login?returnTo=/connect-token");
  }

  const accessToken = session.tokenSet.accessToken;
  const res = await fetch(`${API_URL}/api/v1/auth0/exchange`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    return (
      <Shell>
        <Heading>Sign-in worked, but the token exchange failed</Heading>
        <Body>
          The Stash backend rejected your Auth0 token. Try signing out and back in.
        </Body>
        {detail ? <Pre>{detail.slice(0, 500)}</Pre> : null}
        <Link href="/auth/logout" className="text-[14px] text-brand hover:underline">
          Sign out
        </Link>
      </Shell>
    );
  }

  const data = (await res.json()) as { api_key: string; name: string; display_name?: string };
  const userName = data.display_name || data.name;
  const endpoint = API_URL;

  return (
    <Shell>
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
        Signed in as {userName}
      </p>
      <Heading>Your CLI sign-in token</Heading>
      <Body>
        Paste this into the Claude Code session that&apos;s installing Stash. It&apos;s
        single-use — opening this page again will rotate it.
      </Body>

      <div className="mt-8 overflow-hidden rounded-xl border border-border-subtle bg-inverted">
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-on-inverted-dim">
            sign-in token
          </span>
          <CopyButton value={data.api_key} />
        </div>
        <div className="break-all px-5 py-4 font-mono text-[13px] leading-[1.5] text-on-inverted">
          {data.api_key}
        </div>
      </div>

      <p className="mt-6 text-[14px] leading-[1.6] text-dim">
        Claude will run something like:
      </p>
      <Pre>
        {`stash auth ${endpoint} --api-key <paste>`}
      </Pre>

      <div className="mt-10 flex items-center gap-5 text-[14px]">
        <Link href="/" className="text-dim hover:text-brand">
          ← Back to stash.ac
        </Link>
        <Link href="/auth/logout" className="text-dim hover:text-brand">
          Sign out
        </Link>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[680px] px-6 pb-24 pt-20">{children}</div>
    </main>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h1 className="mt-3 font-display text-[40px] font-black leading-[1.05] tracking-[-0.03em] text-ink">
      {children}
    </h1>
  );
}

function Body({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-4 max-w-[560px] text-[16px] leading-[1.6] text-dim">{children}</p>
  );
}

function Pre({ children }: { children: React.ReactNode }) {
  return (
    <pre className="mt-3 overflow-x-auto rounded-lg bg-raised px-4 py-3 font-mono text-[13px] leading-[1.5] text-ink">
      {children}
    </pre>
  );
}
