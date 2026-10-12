import { Suspense } from "react";
import TraceContextViewer from "@/components/reward-models/TraceContextViewer";
export default async function ContextPage({ params }: { params: Promise<{ traceId: string }> }) {
  const { traceId } = await params;
  return <Suspense fallback={<p>Loading context…</p>}><TraceContextViewer traceId={decodeURIComponent(traceId)} /></Suspense>;
}
