import StashSettingsPageClient from "./StashSettingsPageClient";

export default async function StashSettingsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <StashSettingsPageClient slug={slug} />;
}
