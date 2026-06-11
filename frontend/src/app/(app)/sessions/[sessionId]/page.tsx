import type { Metadata } from "next";
import { Suspense } from "react";

import { SessionDetailSkeleton } from "../../../../components/SkeletonStates";
import {
  firstSearchParam,
  metadataForPublicSkillItem,
} from "../../../../lib/skillMetadata";
import SessionClient from "./SessionClient";

type PageProps = {
  params: Promise<{ sessionId: string }>;
  searchParams: Promise<{ skill?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ sessionId: encodedSessionId }, query] = await Promise.all([params, searchParams]);
  const slug = firstSearchParam(query.skill);
  if (!slug) return { title: "Session - Stash" };

  const sessionId = decodeURIComponent(encodedSessionId);
  return metadataForPublicSkillItem({
    slug,
    itemType: "session",
    itemId: sessionId,
    path: `/sessions/${encodeURIComponent(sessionId)}?skill=${encodeURIComponent(slug)}`,
  });
}

export default function SessionRoute() {
  return (
    <Suspense fallback={<SessionDetailSkeleton />}>
      <SessionClient />
    </Suspense>
  );
}
