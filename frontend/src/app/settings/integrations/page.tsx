"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AccountSettingsSkeleton } from "@/components/SkeletonStates";
import SourceConnectorList from "@/components/integrations/SourceConnectorList";
import WorkspaceShell from "@/components/workspace/workspace-shell";
import { useAuth } from "@/hooks/useAuth";
import { showPersonalIntegrations } from "@/lib/flags";
import { useScope } from "@/lib/scope-store";

export default function PersonalSourcesSettings() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const scope = useScope();
  const allowed = showPersonalIntegrations(user) && scope?.view !== "developer";

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else if (!allowed) router.replace("/settings");
  }, [user, loading, allowed, router]);

  if (loading || !user) return <AccountSettingsSkeleton />;
  if (!allowed) return null;

  return (
    <WorkspaceShell user={user} onLogout={logout}>
      <main className="flex-1 overflow-y-auto px-4 py-7">
        <div className="mx-auto max-w-2xl space-y-5">
          <Link href="/settings" className="text-sm text-muted-foreground hover:text-foreground">
            ← Settings
          </Link>
          <header>
            <h1 className="text-2xl font-semibold text-foreground">Sources</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Connect accounts and choose the sources your agent can read.
            </p>
          </header>
          <SourceConnectorList returnTo="/settings/integrations" />
        </div>
      </main>
    </WorkspaceShell>
  );
}
