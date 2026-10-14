import JudgeWorkspace from "@/components/judge/JudgeWorkspace";

export default async function EvalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <JudgeWorkspace key={id} id={id} />;
}
