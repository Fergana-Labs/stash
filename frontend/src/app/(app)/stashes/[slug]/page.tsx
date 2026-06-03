import type { Metadata } from "next";

import { metadataForPublicStash } from "@/lib/stashMetadata";

import StashPageClient from "./StashPageClient";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const metadata = await metadataForPublicStash({
    slug,
    path: `/stashes/${slug}`,
  });
  return {
    ...metadata,
    alternates: {
      ...metadata.alternates,
      types: {
        "text/markdown": `/stashes/${slug}.md`,
        "application/json": `/stashes/${slug}.json`,
      },
    },
  };
}

export default async function StashPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <>
      <div className="sr-only">
        Agent-readable Stash versions are available at {`/stashes/${slug}.md`} and{" "}
        {`/stashes/${slug}.json`}.
      </div>
      <StashPageClient slug={slug} />
    </>
  );
}
