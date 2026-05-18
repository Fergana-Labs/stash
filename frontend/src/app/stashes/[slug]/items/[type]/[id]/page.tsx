import type { Metadata } from "next";

import StashItemClient from "./StashItemClient";

const BACKEND_ORIGIN = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

async function loadStash(slug: string) {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/stashes/${slug}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; type: string; id: string }>;
}): Promise<Metadata> {
  const { slug, type, id } = await params;
  const data = await loadStash(slug);
  if (!data) return { title: "Stash · Stash" };
  const item = (data.items as { object_type: string; object_id: string; label: string }[]).find(
    (it) => it.object_type === type && it.object_id === id
  );
  const itemLabel = item?.label ?? "Item";
  return { title: `${itemLabel} · ${data.stash.title} · Stash` };
}

export default async function StashItemPage({
  params,
}: {
  params: Promise<{ slug: string; type: string; id: string }>;
}) {
  const { slug, type, id } = await params;
  return <StashItemClient slug={slug} type={type} itemId={id} />;
}
