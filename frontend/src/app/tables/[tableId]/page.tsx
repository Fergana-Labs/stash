import type { Metadata } from "next";

import {
  firstSearchParam,
  metadataForPublicCartridgeItem,
} from "../../../lib/cartridgeMetadata";
import TableClient from "./TableClient";

type PageProps = {
  params: Promise<{ tableId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ tableId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.stash);
  if (!slug) return { title: "Table - Stash" };

  return metadataForPublicCartridgeItem({
    slug,
    itemType: "table",
    itemId: tableId,
    path: `/tables/${tableId}?stash=${encodeURIComponent(slug)}`,
  });
}

export default function TableRoute() {
  return <TableClient />;
}
