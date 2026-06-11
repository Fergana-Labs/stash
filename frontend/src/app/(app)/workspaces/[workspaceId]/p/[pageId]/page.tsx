import { permanentRedirect } from "next/navigation";

// Legacy URL shape. Page links are canonical at /p/[pageId] — the workspace
// is resolved server-side — but old links live on in transcripts and chats.
type PageProps = {
  params: Promise<{ pageId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export default async function LegacyPageRoute({ params, searchParams }: PageProps) {
  const [{ pageId }, query] = await Promise.all([params, searchParams]);
  const stash = Array.isArray(query.stash) ? query.stash[0] : query.stash;
  permanentRedirect(`/p/${pageId}${stash ? `?stash=${encodeURIComponent(stash)}` : ""}`);
}
