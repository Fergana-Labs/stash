import Link from "next/link";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.stash.ac";
const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

type Search = { session?: string };

// Server component. Expects `?session=<id>` from `stash signin`: mints a token
// and POSTs it to /cli-auth/sessions/<id>/approve so the CLI (which is polling)
// can pick it up. Missing session id is a bug, not a user flow.
export default async function ConnectTokenPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const { session: sessionId } = await searchParams;

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

  if (!sessionId) {
    return (
      <Shell>
        <Heading>Open this page from the CLI</Heading>
        <Body>
          This page completes sign-in for <code>stash signin</code> and has to be opened
          with a session id. Run <code>stash signin</code> in your terminal and it&apos;ll
          open the right URL for you.
        </Body>
      </Shell>
    );
  }

  const { auth0 } = await import("@managed/auth0/client");
  const session = await auth0.getSession();
  if (!session) {
    const returnTo = `/connect-token?session=${encodeURIComponent(sessionId)}`;
    redirect(`/auth/login?returnTo=${encodeURIComponent(returnTo)}`);
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

  const approveRes = await fetch(
    `${API_URL}/api/v1/users/cli-auth/sessions/${encodeURIComponent(sessionId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: data.api_key, username: data.name }),
      cache: "no-store",
    },
  );

  if (!approveRes.ok) {
    const detail = await approveRes.text().catch(() => "");
    return (
      <Shell>
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          Signed in as {userName}
        </p>
        <Heading>Could not hand the token to your CLI</Heading>
        <Body>
          Your CLI session may have expired. Re-run <code>stash signin</code> and try again.
        </Body>
        {detail ? <Pre>{detail.slice(0, 500)}</Pre> : null}
      </Shell>
    );
  }

  return (
    <Shell>
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
        Signed in as {userName}
      </p>
      <Heading>You&apos;re signed in.</Heading>
      <Body>
        Head back to your terminal — <code>stash signin</code> has the token and will finish
        wiring up your workspace.
      </Body>
      <Body>You can close this tab.</Body>
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
