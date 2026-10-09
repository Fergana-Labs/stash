import type { Metadata } from "next";
import ModelPlayground from "@/components/reward-models/ModelPlayground";

export const metadata: Metadata = { title: "Model playground - Stash" };

export default async function ModelRoute({ params }: { params: Promise<{ modelId: string }> }) {
  const { modelId } = await params;
  return <ModelPlayground key={modelId} modelId={modelId} />;
}
