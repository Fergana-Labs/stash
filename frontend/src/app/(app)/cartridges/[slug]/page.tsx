import type { Metadata } from "next";

import { metadataForPublicCartridge } from "@/lib/cartridgeMetadata";

import CartridgePageClient from "./CartridgePageClient";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const metadata = await metadataForPublicCartridge({
    slug,
    path: `/cartridges/${slug}`,
  });
  return {
    ...metadata,
    alternates: {
      ...metadata.alternates,
      types: {
        "text/markdown": `/cartridges/${slug}.md`,
        "application/json": `/cartridges/${slug}.json`,
      },
    },
  };
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
