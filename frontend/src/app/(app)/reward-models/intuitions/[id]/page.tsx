import { redirect } from "next/navigation";

export default async function IntuitionPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { id } = await params;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) query.append(key, item);
  }
  redirect(`/reward-models/models/sandbox/${encodeURIComponent(id)}${query.size ? `?${query}` : ""}`);
}
