import type { Metadata } from "next";
import { Suspense } from "react";

import AgentsChat from "@/components/agents/AgentsChat";
import ToolsAndChatGate from "@/components/ToolsAndChatGate";

export const metadata: Metadata = { title: "Chat - Stash" };

export default function AgentsPage() {
  return (
    <ToolsAndChatGate>
      <Suspense>
        <AgentsChat />
      </Suspense>
    </ToolsAndChatGate>
  );
}
