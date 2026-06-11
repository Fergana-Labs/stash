import SkillSettingsPageClient from "./SkillSettingsPageClient";

export default async function SkillSettingsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <SkillSettingsPageClient slug={slug} />;
}
