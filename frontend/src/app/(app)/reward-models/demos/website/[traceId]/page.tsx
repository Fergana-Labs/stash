import WebsiteDemo from "@/components/demos/WebsiteDemo";

export default async function WebsiteDemoPage({
  params,
}: {
  params: Promise<{ traceId: string }>;
}) {
  const { traceId } = await params;
  return <WebsiteDemo key={traceId} traceId={traceId} />;
}
