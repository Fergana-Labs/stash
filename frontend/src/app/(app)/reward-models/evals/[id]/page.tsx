import EvalDestination from "@/components/judge/EvalDestination";

export default async function EvalPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string }> }) {
  const [{ id }, { tab }] = await Promise.all([params, searchParams]);
  return <EvalDestination key={id} id={id} tab={tab} />;
}
