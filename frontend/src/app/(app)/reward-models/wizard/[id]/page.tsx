import Studio from "@/components/judge/Studio";

/** Older wizard links open the same studio as everything else. */
export default async function WizardSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Studio key={id} sessionId={id} />;
}
