import type { Metadata } from "next";
import { Suspense } from "react";

import { FileBrowserSkeleton } from "../../../../../../components/SkeletonStates";
import {
  firstSearchParam,
  metadataForPublicSkillItem,
} from "../../../../../../lib/skillMetadata";
import FolderClient from "./FolderClient";

type PageProps = {
  params: Promise<{ workspaceId: string; folderId: string }>;
  searchParams: Promise<{ skill?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ workspaceId, folderId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.skill);
  if (!slug) return { title: "Folder - Stash" };

  return metadataForPublicSkillItem({
    slug,
    itemType: "folder",
    itemId: folderId,
    path: `/workspaces/${workspaceId}/folders/${folderId}?skill=${encodeURIComponent(slug)}`,
  });
}

export default function FolderRoute() {
  return (
    <Suspense fallback={<FileBrowserSkeleton />}>
      <FolderClient />
    </Suspense>
  );
}
