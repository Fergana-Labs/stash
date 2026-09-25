"use client";

import { type ReactNode, useEffect } from "react";
import DeveloperShell from "@/components/developer/DeveloperShell";
import { useShellChromeValue } from "@/components/ShellChromeContext";
import { usePathname, useRouter } from "next/navigation";
import DeveloperGate from "@/components/developer/DeveloperGate";
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
  const pathname = usePathname();
  const router = useRouter();
  // The console links to these shared viewers for its users' data and sources.
  // DeveloperGate requires a platform workspace before mounting their content.
  const isPlatformResource = /^\/(p|f|folders|tables|sessions|integrations)\/[^/]+$/.test(pathname);
  const redirectToPlatform = user.developer_platform_only &&
    !isPlatformResource && pathname !== "/settings" &&
    pathname !== "/developer" && !pathname.startsWith("/developer/");
  useEffect(() => {
    if (redirectToPlatform) router.replace("/developer");
  }, [redirectToPlatform, router]);
  const scope = useScope();
  const { shareAction } = useShellChromeValue();

  if (redirectToPlatform) return null;

  if (user.developer_platform_only || scope?.view === "developer") {
    return (
      <>
        <DeveloperShell user={user} onLogout={onLogout}>
          {user.developer_platform_only && isPlatformResource
            ? <DeveloperGate>{children}</DeveloperGate>
            : children}
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
          <div className="flex h-full min-h-0 flex-col overflow-hidden border-l border-t border-border bg-base shadow-[-10px_-6px_28px_-16px_rgba(30,25,15,0.10)]">
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
