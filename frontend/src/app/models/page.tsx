"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import WorkspaceShell from "@/components/workspace/workspace-shell";
import TrainedModels from "@/components/tools/TrainedModels";
import { AccountSettingsSkeleton } from "@/components/SkeletonStates";
import { useAuth } from "@/hooks/useAuth";

// Models trained on the user's own material. A management page like
// Settings (its own route, the shared shell, no explorer section): the Tools
// page is gated to two orgs, and this has to reach everyone who can pay for
// a training run. Agents never come here — they use the skill's MCP server.
export default function ModelsPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) return <AccountSettingsSkeleton />;

  return (
    <WorkspaceShell user={user} onLogout={logout}>
      <main className="flex-1 overflow-y-auto px-4 py-10">
        <div className="mx-auto w-full max-w-2xl space-y-6">
          <button
            type="button"
            onClick={() => router.push("/")}
            className="inline-flex cursor-pointer items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <span aria-hidden>←</span> Home
          </button>
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Models</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Models trained on your own writing. Your agent uses them through the skill that
              brings them; this is where you train one and try it. Training sends the passages
              you pick to our GPU provider and nowhere else.
            </p>
          </div>
          <TrainedModels />
        </div>
      </main>
    </WorkspaceShell>
  );
}
