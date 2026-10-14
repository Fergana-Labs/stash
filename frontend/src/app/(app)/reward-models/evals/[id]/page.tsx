import Studio from "@/components/judge/Studio";

export default async function IntuitionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Studio key={id} modelId={id} />;
}
