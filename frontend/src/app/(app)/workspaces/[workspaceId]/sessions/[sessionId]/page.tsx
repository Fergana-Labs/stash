import { permanentRedirect } from "next/navigation";

// Legacy URL shape. Session links are canonical at /sessions/[sessionId] —
// the workspace is resolved server-side — but old links live on in
// transcripts and chats.
type PageProps = {
  params: Promise<{ sessionId: string }>;
  searchParams: Promise<{ skill?: string | string[] }>;
};

export default async function LegacySessionRoute({ params, searchParams }: PageProps) {
  const [{ sessionId }, query] = await Promise.all([params, searchParams]);
  const skill = Array.isArray(query.skill) ? query.skill[0] : query.skill;
  permanentRedirect(
    `/sessions/${sessionId}${skill ? `?skill=${encodeURIComponent(skill)}` : ""}`
  );
}
