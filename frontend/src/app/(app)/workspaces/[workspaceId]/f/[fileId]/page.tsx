import { permanentRedirect } from "next/navigation";

// Legacy URL shape. File links are canonical at /f/[fileId] — the workspace
// is resolved server-side — but old links live on in transcripts and chats.
type PageProps = {
  params: Promise<{ fileId: string }>;
  searchParams: Promise<{ skill?: string | string[] }>;
};

export default async function LegacyFileRoute({ params, searchParams }: PageProps) {
  const [{ fileId }, query] = await Promise.all([params, searchParams]);
  const skill = Array.isArray(query.skill) ? query.skill[0] : query.skill;
  permanentRedirect(`/f/${fileId}${skill ? `?skill=${encodeURIComponent(skill)}` : ""}`);
}
