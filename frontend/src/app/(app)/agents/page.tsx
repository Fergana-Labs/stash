import type { Metadata } from "next";
import { Suspense } from "react";

import AgentsChat from "@/components/agents/AgentsChat";

export const metadata: Metadata = { title: "Chat - Stash" };

export default function AgentsPage() {
  return (
    <Suspense>
      <AgentsChat />
    </Suspense>
  );
}
