import type { Metadata } from "next";

import AppView from "@/components/apps/AppView";

type PageProps = { params: Promise<{ slug: string }> };

export const metadata: Metadata = { title: "Apps - Stash" };

/** /apps/<slug> — the stable, nameable URL for a mini program. The slug
 *  resolves server-side to *this user's* table, so the link is shareable
 *  between a user's own devices without leaking a table UUID. */
export default async function AppRoute({ params }: PageProps) {
  const { slug } = await params;
  return <AppView slug={slug} />;
}
