import type { Metadata } from "next";
import { notFound } from "next/navigation";

import HomePage, { type HeroCopy } from "../../_components/HomePage";

// Message-test landing pages: the homepage with one variable changed (hero
// copy), every signup CTA routed into the lead survey. One X ad points at
// each slug; survey submissions arrive tagged with it.
const VARIANTS: Record<string, HeroCopy> = {
  drive: {
    headline: "The Drive for your AI agents.",
    subhead:
      "Markdown, HTML, sessions, and skills — a virtual file system your agents work in.",
  },
  wiki: {
    headline: "A wiki your agents read and write.",
  },
  connect: {
    headline: "Connect your agents to all your data sources.",
  },
  assistant: {
    headline: "An AI assistant that lives in Slack and email.",
  },
};

export function generateStaticParams() {
  return Object.keys(VARIANTS).map((variant) => ({ variant }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ variant: string }>;
}): Promise<Metadata> {
  const { variant } = await params;
  const copy = VARIANTS[variant];
  if (!copy) return {};
  return {
    title: `Stash · ${copy.headline}`,
    robots: { index: false },
  };
}

export default async function VariantPage({
  params,
}: {
  params: Promise<{ variant: string }>;
}) {
  const { variant } = await params;
  const copy = VARIANTS[variant];
  if (!copy) notFound();
  return <HomePage heroOverride={copy} surveyVariant={variant} />;
}
