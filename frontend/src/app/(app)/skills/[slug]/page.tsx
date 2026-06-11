import type { Metadata } from "next";

import { metadataForPublicSkill } from "@/lib/skillMetadata";

import SkillPageClient from "./SkillPageClient";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const metadata = await metadataForPublicSkill({
    slug,
    path: `/skills/${slug}`,
  });
  return {
    ...metadata,
    alternates: {
      ...metadata.alternates,
      types: {
        "text/markdown": `/skills/${slug}.md`,
        "application/json": `/skills/${slug}.json`,
      },
    },
  };
}

export default async function SkillPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <>
      <div className="sr-only">
        Agent-readable skill versions are available at {`/skills/${slug}.md`} and{" "}
        {`/skills/${slug}.json`}.
      </div>
      <SkillPageClient slug={slug} />
    </>
  );
}
