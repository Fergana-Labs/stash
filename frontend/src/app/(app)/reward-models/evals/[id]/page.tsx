import EvalDestination from "@/components/judge/EvalDestination";

export default async function EvalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <EvalDestination key={id} id={id} />;
}
