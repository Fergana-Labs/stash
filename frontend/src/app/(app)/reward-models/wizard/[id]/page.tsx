import WizardChat from "@/components/wizard/WizardChat";

export default async function WizardSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WizardChat key={id} sessionId={id} />;
}
