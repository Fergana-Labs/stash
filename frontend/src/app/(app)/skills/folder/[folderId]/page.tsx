import type { Metadata } from "next";
import { Suspense } from "react";

import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import SkillFolderClient from "./SkillFolderClient";

export const metadata: Metadata = { title: "Skill - Stash" };

export default function SkillFolderRoute() {
  return (
    <Suspense fallback={<FileBrowserSkeleton />}>
      <SkillFolderClient />
    </Suspense>
  );
}
