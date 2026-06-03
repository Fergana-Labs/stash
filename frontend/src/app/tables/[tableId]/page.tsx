import type { Metadata } from "next";

import {
  firstSearchParam,
  metadataForPublicCartridgeItem,
} from "../../../lib/cartridgeMetadata";
import TableClient from "./TableClient";

type PageProps = {
  params: Promise<{ tableId: string }>;
  searchParams: Promise<{
    stash?: string | string[];
    workspaceId?: string | string[];
  }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ tableId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.stash);
  if (!slug) return { title: "Table - Stash" };

  const workspaceId = firstSearchParam(query.workspaceId);
  const workspacePart = workspaceId ? `&workspaceId=${encodeURIComponent(workspaceId)}` : "";
  return metadataForPublicCartridgeItem({
    slug,
    itemType: "table",
    itemId: tableId,
    path: `/tables/${tableId}?stash=${encodeURIComponent(slug)}${workspacePart}`,
  });
}

export default function TableRoute() {
  return <TableClient />;
}
