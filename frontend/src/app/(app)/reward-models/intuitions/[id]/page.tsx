"use client";

import { Suspense, use } from "react";
import { RmPageSkeleton } from "@/components/reward-models/RmSkeletons";
import IntuitionDetail from "@/components/intuitions/IntuitionDetail";

export default function IntuitionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Suspense fallback={<RmPageSkeleton />}>
      <IntuitionDetail id={decodeURIComponent(id)} />
    </Suspense>
  );
}
