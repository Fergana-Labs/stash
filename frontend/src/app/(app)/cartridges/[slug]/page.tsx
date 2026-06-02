import type { Metadata } from "next";

import { SSR_BACKEND_ORIGIN as BACKEND_ORIGIN } from "@/lib/backendOrigin";

import CartridgePageClient from "./CartridgePageClient";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const data = await loadPublicCartridge(slug);
  if (!data) return { title: "Stash · Stash" };
  const title = `${data.stash.title} · Stash`;
  const description =
    data.stash.description ||
    `A cartridge of ${data.items.length} item${data.items.length === 1 ? "" : "s"} from ${data.workspace_name}.`;
  return {
    title,
    description,
    alternates: {
      canonical: `/cartridges/${slug}`,
      types: {
        "text/markdown": `/cartridges/${slug}.md`,
        "application/json": `/cartridges/${slug}.json`,
      },
    },
    openGraph: {
      title,
      description,
      type: "article",
      url: `/cartridges/${slug}`,
      siteName: "Stash",
    },
    twitter: { card: "summary_large_image", title, description },
  };
}

async function loadPublicCartridge(slug: string) {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/cartridges/${slug}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

export default async function CartridgePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <>
      <div className="sr-only">
        Agent-readable cartridge versions are available at {`/cartridges/${slug}.md`} and{" "}
        {`/cartridges/${slug}.json`}.
      </div>
      <CartridgePageClient slug={slug} />
    </>
  );
}
