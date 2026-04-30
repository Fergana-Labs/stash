import { redirect } from "next/navigation";
import Link from "next/link";

import TranscriptViewer from "./TranscriptViewer";

export const dynamic = "force-dynamic";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";
const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

export default async function HistorySessionPage({
  params,
}: {
  params: Promise<{ workspaceId: string; sessionId: string }>;
}) {
  const { workspaceId, sessionId } = await params;

  if (!AUTH0_ENABLED) {
    return (
      <Shell>
        <p className="text-dim">Sign-in is not configured on this deployment.</p>
      </Shell>
    );
  }

  const { auth0 } = await import("@managed/auth0/client");
  const returnTo = `/history/${workspaceId}/${sessionId}`;

  const session = await auth0.getSession();
  if (!session) {
    redirect(`/auth/login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  let accessToken: string;
  try {
    const tokenResponse = await auth0.getAccessToken();
    accessToken = tokenResponse.token;
  } catch {
    redirect(`/auth/login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  return (
    <Shell>
      <div className="mb-4 flex items-center justify-between">
        <Link href="/" className="font-display text-[16px] font-bold text-ink hover:text-brand">
          stash
        </Link>
        <span className="font-mono text-[11px] text-muted">
          {(session.user?.email as string) || ""}
        </span>
      </div>
      <TranscriptViewer
        apiUrl={API_URL}
        workspaceId={workspaceId}
        sessionId={sessionId}
        accessToken={accessToken}
      />
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[720px] px-6 pb-24 pt-12">{children}</div>
    </main>
  );
}
