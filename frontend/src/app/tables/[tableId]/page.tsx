import type { Metadata } from "next";
import { Suspense } from "react";

import { TableEditorSkeleton } from "@/components/SkeletonStates";
import {
  firstSearchParam,
  metadataForPublicSkillItem,
} from "../../../lib/skillMetadata";
import TableRouteClient from "./TableRouteClient";

type PageProps = {
  params: Promise<{ tableId: string }>;
  searchParams: Promise<{ skill?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ tableId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.skill);
  if (!slug) return { title: "Table - Stash" };

  return metadataForPublicSkillItem({
    slug,
    itemType: "table",
    itemId: tableId,
    path: `/tables/${tableId}?skill=${encodeURIComponent(slug)}`,
  });
}

export default async function TableRoute({ params }: PageProps) {
  const { tableId } = await params;
  return (
    <Suspense fallback={<TableEditorSkeleton />}>
      <TableRouteClient tableId={tableId} />
    </Suspense>
  );
}
