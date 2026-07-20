import type { Metadata } from "next";
import { headers } from "next/headers";

import { loadPublicSkillPreview } from "./skillPreviewFetch";
import { skillItemPath } from "./localSkill";
import {
  findSkillItem,
  isSkillItemType,
  itemMetadataDescription,
  itemMetadataTitle,
  skillMetadataDescription,
  skillMetadataTitle,
  skillOgImagePath,
  type SkillItemType,
} from "./skillPreview";

type MetadataInput = {
  slug: string;
  path: string;
};

type ItemMetadataInput = {
  slug: string;
  itemType: SkillItemType;
  itemId: string;
};

export async function metadataForPublicSkill({
  slug,
  path,
}: MetadataInput): Promise<Metadata> {
  const data = await loadPublicSkillPreview(slug);
  if (!data) return { title: "Skill - Skill" };

  const title = skillMetadataTitle(data);
  const description = skillMetadataDescription(data);
  return metadataForPreview({
    title,
    description,
    path,
    imagePath: skillOgImagePath(slug),
  });
}

export async function metadataForPublicSkillItem({
  slug,
  itemType,
  itemId,
}: ItemMetadataInput): Promise<Metadata> {
  const data = await loadPublicSkillPreview(slug);
  if (!data) return { title: "Skill - Skill" };

  const item = findSkillItem(data.contents, itemType, itemId);
  if (!item) return metadataForPublicSkill({ slug, path: `/skills/${slug}` });

  const title = itemMetadataTitle(data, item);
  const description = itemMetadataDescription(data, item);
  return metadataForPreview({
    title,
    description,
    path: skillItemPath(itemType, itemId, slug),
    imagePath: skillOgImagePath(slug, itemType, itemId),
  });
}

export function firstSearchParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

export function typedSearchParam(value: string | string[] | undefined): SkillItemType | null {
  const first = firstSearchParam(value);
  return isSkillItemType(first) ? first : null;
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
      siteName: "Skill",
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
