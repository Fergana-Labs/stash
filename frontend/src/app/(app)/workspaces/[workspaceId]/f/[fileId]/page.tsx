import type { Metadata } from "next";

import {
  firstSearchParam,
  metadataForPublicStashItem,
} from "../../../../../../lib/stashMetadata";
import FileClient from "./FileClient";

type PageProps = {
  params: Promise<{ workspaceId: string; fileId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ workspaceId, fileId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.stash);
  if (!slug) return { title: "File - Stash" };

  return metadataForPublicStashItem({
    slug,
    itemType: "file",
    itemId: fileId,
    path: `/workspaces/${workspaceId}/f/${fileId}?stash=${encodeURIComponent(slug)}`,
  });
}

export default function FileRoute() {
  return <FileClient />;
}
