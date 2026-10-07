"use client";

import { use } from "react";
import OptimizationDetail from "@/components/optimization/OptimizationDetail";

export default function OptimizationDetailPage({ params }: { params: Promise<{ optimizationId: string }> }) {
  const { optimizationId } = use(params);
  return <OptimizationDetail id={optimizationId} />;
}
