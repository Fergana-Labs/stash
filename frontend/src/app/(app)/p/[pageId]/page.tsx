import type { Metadata } from "next";
import { Suspense } from "react";

import { DocumentPageSkeleton } from "../../../../components/SkeletonStates";
import {
  firstSearchParam,
  metadataForPublicCartridgeItem,
} from "../../../../lib/cartridgeMetadata";
import PageClient from "./PageClient";

type PageProps = {
  params: Promise<{ pageId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ pageId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.stash);
  if (!slug) return { title: "Page - Stash" };

  return metadataForPublicCartridgeItem({
    slug,
    itemType: "page",
    itemId: pageId,
    path: `/p/${pageId}?stash=${encodeURIComponent(slug)}`,
  });
}

export default function PageRoute() {
  return (
    <Suspense fallback={<DocumentPageSkeleton />}>
      <PageClient />
    </Suspense>
  );
}
