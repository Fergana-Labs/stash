import type { Metadata } from "next";
import { Suspense } from "react";

import { FileBrowserSkeleton } from "../../../../../../components/SkeletonStates";
import {
  firstSearchParam,
  metadataForPublicStashItem,
} from "../../../../../../lib/stashMetadata";
import FolderClient from "./FolderClient";

type PageProps = {
  params: Promise<{ workspaceId: string; folderId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ workspaceId, folderId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.stash);
  if (!slug) return { title: "Folder - Stash" };

  return metadataForPublicStashItem({
    slug,
    itemType: "folder",
    itemId: folderId,
    path: `/workspaces/${workspaceId}/folders/${folderId}?stash=${encodeURIComponent(slug)}`,
  });
}

export default function FolderRoute() {
  return (
    <Suspense fallback={<FileBrowserSkeleton />}>
      <FolderClient />
    </Suspense>
  );
}
