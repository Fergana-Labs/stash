import { permanentRedirect } from "next/navigation";

// Legacy URL shape. Page links are canonical at /p/[pageId] — the workspace
// is resolved server-side — but old links live on in transcripts and chats.
type PageProps = {
  params: Promise<{ pageId: string }>;
  searchParams: Promise<{ skill?: string | string[] }>;
};

export default async function LegacyPageRoute({ params, searchParams }: PageProps) {
  const [{ pageId }, query] = await Promise.all([params, searchParams]);
  const skill = Array.isArray(query.skill) ? query.skill[0] : query.skill;
  permanentRedirect(`/p/${pageId}${skill ? `?skill=${encodeURIComponent(skill)}` : ""}`);
}
