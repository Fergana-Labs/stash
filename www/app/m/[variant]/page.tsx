import type { Metadata } from "next";
import { notFound } from "next/navigation";

import VariantLanding from "../_components/VariantLanding";
import { VARIANTS } from "../variants";

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
  return <VariantLanding variant={variant} copy={copy} />;
}
