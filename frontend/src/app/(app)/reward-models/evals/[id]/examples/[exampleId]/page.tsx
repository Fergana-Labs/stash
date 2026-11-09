import EvalExample from "@/components/evals/judge/EvalExample";

export default async function EvalExamplePage({ params }: { params: Promise<{ id: string; exampleId: string }> }) {
  const { id, exampleId } = await params;
  return <EvalExample key={exampleId} evalId={id} exampleId={exampleId} />;
}
