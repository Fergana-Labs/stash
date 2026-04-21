import Link from "next/link";
import { redirect } from "next/navigation";

import ConnectTokenClient from "./ConnectTokenClient";

export const dynamic = "force-dynamic";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";
const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

type Search = { session?: string; device?: string };

// Server-side gate: confirm Auth0 session, then hand off to the client
// component which shows an explicit "Authorize CLI" confirmation before
// minting any token. We used to do the whole exchange+approve dance during
// SSR, which silently handed the CLI a token just because a browser session
// happened to exist — no confirmation, no chance to switch accounts.
export default async function ConnectTokenPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const { session: sessionId, device } = await searchParams;

  if (!AUTH0_ENABLED) {
    return (
      <Shell>
        <Heading>Sign-in is not configured</Heading>
        <Body>
          This deployment of joinstash.ai doesn&apos;t have <code>NEXT_PUBLIC_AUTH0_ENABLED</code>{" "}
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
    const qs = new URLSearchParams({ session: sessionId });
    if (device) qs.set("device", device);
    const returnTo = `/connect-token?${qs.toString()}`;
    redirect(`/auth/login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  const userName =
    (session.user?.name as string | undefined) ||
    (session.user?.email as string | undefined) ||
    "your account";

  return (
    <Shell>
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
        Signed in as {userName}
      </p>
      <Heading>Authorize the Stash CLI?</Heading>
      <Body>
        A new API key scoped to this terminal will be minted and handed to your CLI.
        You can revoke it anytime from account settings.
      </Body>
      <ConnectTokenClient
        apiUrl={API_URL}
        sessionId={sessionId}
        device={device}
        userName={userName}
      />
      <Link href="/auth/logout" className="mt-6 inline-block text-[14px] text-brand hover:underline">
        Use a different account
      </Link>
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
