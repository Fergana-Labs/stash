import type { Metadata } from "next";
import { Suspense } from "react";

import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import SkillFolderClient from "./SkillFolderClient";

export const metadata: Metadata = { title: "Skill - Stash" };

export default async function SkillFolderRoute({ params }: { params: Promise<{ folderId: string }> }) {
  const { folderId } = await params;
  return (
    <Suspense fallback={<FileBrowserSkeleton />}>
      <SkillFolderClient folderId={folderId} />
    </Suspense>
  );
}
