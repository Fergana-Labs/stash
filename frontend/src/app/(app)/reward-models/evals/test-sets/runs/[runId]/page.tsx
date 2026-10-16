import RunClient from "@/components/test-sets/RunClient";

export default async function TestRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <RunClient key={runId} runId={runId} />;
}
