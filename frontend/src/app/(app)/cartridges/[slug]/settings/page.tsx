import CartridgeSettingsPageClient from "./CartridgeSettingsPageClient";

export default async function CartridgeSettingsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <CartridgeSettingsPageClient slug={slug} />;
}
