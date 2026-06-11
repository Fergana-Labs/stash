import { permanentRedirect } from "next/navigation";

// Legacy URL shape. Session links are canonical at /sessions/[sessionId] —
// the workspace is resolved server-side — but old links live on in
// transcripts and chats.
type PageProps = {
  params: Promise<{ sessionId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export default async function LegacySessionRoute({ params, searchParams }: PageProps) {
  const [{ sessionId }, query] = await Promise.all([params, searchParams]);
  const stash = Array.isArray(query.stash) ? query.stash[0] : query.stash;
  permanentRedirect(
    `/sessions/${sessionId}${stash ? `?stash=${encodeURIComponent(stash)}` : ""}`
  );
}
