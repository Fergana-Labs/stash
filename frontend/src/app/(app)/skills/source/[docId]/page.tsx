import type { Metadata } from "next";
import { Suspense } from "react";

import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import SourceSkillClient from "./SourceSkillClient";

export const metadata: Metadata = { title: "Skill - Stash" };

export default async function SourceSkillRoute({
  params,
}: {
  params: Promise<{ docId: string }>;
}) {
  const { docId } = await params;
  return (
    <Suspense fallback={<FileBrowserSkeleton />}>
      <SourceSkillClient docId={docId} />
    </Suspense>
  );
}
