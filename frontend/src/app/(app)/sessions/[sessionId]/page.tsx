import type { Metadata } from "next";
import { Suspense } from "react";

import { SessionDetailSkeleton } from "@/components/SkeletonStates";
import SessionClient from "./SessionClient";

export const metadata: Metadata = { title: "Session - Stash" };

export default async function SessionRoute({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return (
    <Suspense fallback={<SessionDetailSkeleton />}>
      <SessionClient sessionId={decodeURIComponent(sessionId)} />
    </Suspense>
  );
}
