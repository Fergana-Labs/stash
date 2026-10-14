import TestSetClient from "@/components/test-sets/TestSetClient";

export default async function TestSetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TestSetClient key={id} id={id} />;
}
