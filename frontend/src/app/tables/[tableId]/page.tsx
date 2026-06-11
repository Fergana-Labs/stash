import type { Metadata } from "next";

import {
  firstSearchParam,
  metadataForPublicSkillItem,
} from "../../../lib/skillMetadata";
import TableClient from "./TableClient";

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

export default function TableRoute() {
  return <TableClient />;
}
