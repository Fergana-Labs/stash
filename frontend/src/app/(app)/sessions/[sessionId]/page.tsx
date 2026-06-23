import type { Metadata } from "next";
import { Suspense } from "react";

import { SessionDetailSkeleton } from "@/components/SkeletonStates";
import SessionClient from "./SessionClient";

export const metadata: Metadata = { title: "Session - Stash" };

export default function SessionRoute() {
  return (
    <Suspense fallback={<SessionDetailSkeleton />}>
      <SessionClient />
    </Suspense>
  );
}
