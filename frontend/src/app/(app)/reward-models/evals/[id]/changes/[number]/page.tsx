import EvalChange from "@/components/evals/judge/EvalChange";

export default async function EvalChangePage({ params, searchParams }: { params: Promise<{ id: string; number: string }>; searchParams: Promise<{ tab?: string }> }) {
  const [{ id, number }, { tab }] = await Promise.all([params, searchParams]);
  return <EvalChange key={`${id}:${number}`} evalId={id} number={Number(number)} initialTab={tab} />;
}
