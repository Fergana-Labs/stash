import type { Metadata } from "next";
import TraceClient from "./TraceClient";

export const metadata: Metadata = { title: "Trace - Stash" };

export default async function TraceRoute({ params }: { params: Promise<{ traceId: string }> }) {
  const { traceId } = await params;
  return <TraceClient traceId={decodeURIComponent(traceId)} />;
}
