"use client";

import type { ReactNode } from "react";
import DeveloperShell from "@/components/developer/DeveloperShell";
import { useShellChromeValue } from "@/components/ShellChromeContext";
import { Toaster } from "@/components/ui/sonner";
import { useScope } from "@/lib/scope-store";
import type { User } from "@/lib/types";
import Rail from "./rail";
import Topbar from "./topbar";

export default function WorkspaceShell({
  user,
  onLogout,
  children,
}: {
  user: User;
  onLogout: () => void;
  children: ReactNode;
}) {
  const scope = useScope();
  const { shareAction } = useShellChromeValue();

  if (scope?.view === "developer") {
    return (
      <>
        <DeveloperShell user={user} onLogout={onLogout}>
          {children}
        </DeveloperShell>
        <Toaster />
      </>
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-sidebar">
      <Topbar />
      <div className="flex min-h-0 flex-1">
        <Rail user={user} onLogout={onLogout} />
        <div className="min-w-0 flex-1">
          <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-tl-2xl border-l border-t border-border bg-base shadow-[-10px_-6px_28px_-16px_rgba(30,25,15,0.10)]">
            {shareAction && (
              <div className="flex h-10 shrink-0 items-center justify-end border-b border-border px-4">
                {shareAction}
              </div>
            )}
            <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {children}
            </main>
          </div>
        </div>
      </div>
      <Toaster />
    </div>
  );
}
