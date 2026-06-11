import type { Metadata } from "next";
import { Suspense } from "react";

import { DocumentPageSkeleton } from "../../../../components/SkeletonStates";
import {
  firstSearchParam,
  metadataForPublicSkillItem,
} from "../../../../lib/skillMetadata";
import PageClient from "./PageClient";

type PageProps = {
  params: Promise<{ pageId: string }>;
  searchParams: Promise<{ skill?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ pageId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.skill);
  if (!slug) return { title: "Page - Stash" };

  return metadataForPublicSkillItem({
    slug,
    itemType: "page",
    itemId: pageId,
    path: `/p/${pageId}?skill=${encodeURIComponent(slug)}`,
  });
}

export default function PageRoute() {
  return (
    <Suspense fallback={<DocumentPageSkeleton />}>
      <PageClient />
    </Suspense>
  );
}
