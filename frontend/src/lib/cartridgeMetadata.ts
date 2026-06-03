import type { Metadata } from "next";
import { headers } from "next/headers";

import { loadPublicCartridgePreview } from "./cartridgePreviewFetch";
import {
  findCartridgeItem,
  isCartridgeItemType,
  itemMetadataDescription,
  itemMetadataTitle,
  cartridgeMetadataDescription,
  cartridgeMetadataTitle,
  cartridgeOgImagePath,
  type CartridgeItemType,
} from "./cartridgePreview";

type MetadataInput = {
  slug: string;
  path: string;
};

type ItemMetadataInput = MetadataInput & {
  itemType: CartridgeItemType;
  itemId: string;
};

export async function metadataForPublicCartridge({
  slug,
  path,
}: MetadataInput): Promise<Metadata> {
  const data = await loadPublicCartridgePreview(slug);
  if (!data) return { title: "Stash - Stash" };

  const title = cartridgeMetadataTitle(data);
  const description = cartridgeMetadataDescription(data);
  return metadataForPreview({
    title,
    description,
    path,
    imagePath: cartridgeOgImagePath(slug),
  });
}

export async function metadataForPublicCartridgeItem({
  slug,
  itemType,
  itemId,
  path,
}: ItemMetadataInput): Promise<Metadata> {
  const data = await loadPublicCartridgePreview(slug);
  if (!data) return { title: "Stash - Stash" };

  const item = findCartridgeItem(data.items, itemType, itemId);
  if (!item) return metadataForPublicCartridge({ slug, path: `/cartridges/${slug}` });

  const title = itemMetadataTitle(data, item);
  const description = itemMetadataDescription(data, item);
  return metadataForPreview({
    title,
    description,
    path,
    imagePath: cartridgeOgImagePath(slug, itemType, itemId),
  });
}

export function firstSearchParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

export function typedSearchParam(value: string | string[] | undefined): CartridgeItemType | null {
  const first = firstSearchParam(value);
  return isCartridgeItemType(first) ? first : null;
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
