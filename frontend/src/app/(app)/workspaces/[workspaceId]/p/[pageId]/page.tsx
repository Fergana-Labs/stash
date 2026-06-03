import type { Metadata } from "next";
import { Suspense } from "react";

import { DocumentPageSkeleton } from "../../../../../../components/SkeletonStates";
import {
  firstSearchParam,
  metadataForPublicStashItem,
} from "../../../../../../lib/stashMetadata";
import PageClient from "./PageClient";

type PageProps = {
  params: Promise<{ workspaceId: string; pageId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ workspaceId, pageId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.stash);
  if (!slug) return { title: "Page - Stash" };

  return metadataForPublicStashItem({
    slug,
    itemType: "page",
    itemId: pageId,
    path: `/workspaces/${workspaceId}/p/${pageId}?stash=${encodeURIComponent(slug)}`,
  });
}

export default function PageRoute() {
  return (
    <Suspense fallback={<DocumentPageSkeleton />}>
      <PageClient />
    </Suspense>
  );
}
