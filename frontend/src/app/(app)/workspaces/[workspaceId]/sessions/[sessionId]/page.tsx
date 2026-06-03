import type { Metadata } from "next";
import { Suspense } from "react";

import { SessionDetailSkeleton } from "../../../../../../components/SkeletonStates";
import {
  firstSearchParam,
  metadataForPublicCartridgeItem,
} from "../../../../../../lib/cartridgeMetadata";
import SessionClient from "./SessionClient";

type PageProps = {
  params: Promise<{ workspaceId: string; sessionId: string }>;
  searchParams: Promise<{ stash?: string | string[] }>;
};

export async function generateMetadata({
  params,
  searchParams,
}: PageProps): Promise<Metadata> {
  const [{ workspaceId, sessionId: encodedSessionId }, query] = await Promise.all([
    params,
    searchParams,
  ]);
  const slug = firstSearchParam(query.stash);
  if (!slug) return { title: "Session - Stash" };

  const sessionId = decodeURIComponent(encodedSessionId);
  return metadataForPublicCartridgeItem({
    slug,
    itemType: "session",
    itemId: sessionId,
    path: `/workspaces/${workspaceId}/sessions/${encodeURIComponent(
      sessionId,
    )}?stash=${encodeURIComponent(slug)}`,
  });
}

export default function SessionRoute() {
  return (
    <Suspense fallback={<SessionDetailSkeleton />}>
      <SessionClient />
    </Suspense>
  );
}
