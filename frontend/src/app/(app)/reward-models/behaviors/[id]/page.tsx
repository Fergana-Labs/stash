import BehaviorClient from "./BehaviorClient";

export default async function BehaviorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BehaviorClient key={id} id={id} />;
}
