import type { Metadata } from "next";

import {
  firstSearchParam,
  metadataForPublicSkillItem,
} from "@/lib/skillMetadata";
import FileClient from "./FileClient";

type PageProps = {
  params: Promise<{ fileId: string }>;
  searchParams: Promise<{ skill?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ fileId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.skill);
  if (!slug) return { title: "File - Stash" };

  return metadataForPublicSkillItem({
    slug,
    itemType: "file",
    itemId: fileId,
    path: `/f/${fileId}?skill=${encodeURIComponent(slug)}`,
  });
}

export default function FileRoute() {
  return <FileClient />;
}
