import { permanentRedirect } from "next/navigation";

// Legacy URL shape. File links are canonical at /f/[fileId] — the workspace
// is resolved server-side — but old links live on in transcripts and chats.
type PageProps = {
  params: Promise<{ fileId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export default async function LegacyFileRoute({ params, searchParams }: PageProps) {
  const [{ fileId }, query] = await Promise.all([params, searchParams]);
  const stash = Array.isArray(query.stash) ? query.stash[0] : query.stash;
  permanentRedirect(`/f/${fileId}${stash ? `?stash=${encodeURIComponent(stash)}` : ""}`);
}
