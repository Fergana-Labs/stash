import Studio from "@/components/judge/Studio";

/** A new intuition starts as a conversation; the wizard creates the model as it goes. */
export default async function NewIntuitionPage({ searchParams }: { searchParams: Promise<{ session?: string }> }) {
  const { session } = await searchParams;
  return <Studio key={session ?? "new"} sessionId={session ?? null} />;
}
