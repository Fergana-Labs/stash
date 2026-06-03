import type { Metadata } from "next";
import { headers } from "next/headers";

import { loadPublicStashPreview } from "./stashPreviewFetch";
import {
  findStashItem,
  isStashItemType,
  itemMetadataDescription,
  itemMetadataTitle,
  stashMetadataDescription,
  stashMetadataTitle,
  stashOgImagePath,
  type StashItemType,
} from "./stashPreview";

type MetadataInput = {
  slug: string;
  path: string;
};

type ItemMetadataInput = MetadataInput & {
  itemType: StashItemType;
  itemId: string;
};

export async function metadataForPublicStash({
  slug,
  path,
}: MetadataInput): Promise<Metadata> {
  const data = await loadPublicStashPreview(slug);
  if (!data) return { title: "Stash - Stash" };

  const title = stashMetadataTitle(data);
  const description = stashMetadataDescription(data);
  return metadataForPreview({
    title,
    description,
    path,
    imagePath: stashOgImagePath(slug),
  });
}

export async function metadataForPublicStashItem({
  slug,
  itemType,
  itemId,
  path,
}: ItemMetadataInput): Promise<Metadata> {
  const data = await loadPublicStashPreview(slug);
  if (!data) return { title: "Stash - Stash" };

  const item = findStashItem(data.items, itemType, itemId);
  if (!item) return metadataForPublicStash({ slug, path: `/cartridges/${slug}` });

  const title = itemMetadataTitle(data, item);
  const description = itemMetadataDescription(data, item);
  return metadataForPreview({
    title,
    description,
    path,
    imagePath: stashOgImagePath(slug, itemType, itemId),
  });
}

export function firstSearchParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

export function typedSearchParam(value: string | string[] | undefined): StashItemType | null {
  const first = firstSearchParam(value);
  return isStashItemType(first) ? first : null;
}

async function metadataForPreview({
  title,
  description,
  path,
  imagePath,
}: {
  title: string;
  description: string;
  path: string;
  imagePath: string;
}): Promise<Metadata> {
  const origin = await requestOrigin();
  const url = `${origin}${path}`;
  const imageUrl = `${origin}${imagePath}`;
  return {
    title,
    description,
    alternates: {
      canonical: url,
    },
    openGraph: {
      title,
      description,
      type: "article",
      url,
      siteName: "Stash",
      images: [
        {
          url: imageUrl,
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [imageUrl],
    },
  };
}

async function requestOrigin(): Promise<string> {
  const requestHeaders = await headers();
  const configured = process.env.PUBLIC_URL || process.env.NEXT_PUBLIC_APP_URL;
  const host =
    requestHeaders.get("x-forwarded-host")?.split(",")[0]?.trim() ??
    requestHeaders.get("host");

  if (!host) return (configured || "http://localhost:3457").replace(/\/$/, "");

  const forwardedProto = requestHeaders.get("x-forwarded-proto")?.split(",")[0]?.trim();
  const proto = forwardedProto || (host.startsWith("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}
