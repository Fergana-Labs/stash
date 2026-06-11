"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ReactNode, useEffect } from "react";

import AppShell from "../../components/AppShell";
import {
  AppShellSkeleton,
  PublicCartridgeSkeleton,
} from "../../components/SkeletonStates";
import { useAuth } from "../../hooks/useAuth";

// Shared chrome for the signed-in app. Hosting AppShell here (rather than
// inside each subtree's layout or page) keeps the sidebar mounted as you move
// between /cartridges/[slug] and /workspaces/[workspaceId], so scroll position
// and folder-open state survive the navigation. Public stash routes are
// readable when signed out, so we render their children bare in that case.
//
// A workspace deep link with `?stash=<slug>` is also a public-stash route:
// the page/session/file viewers fall back to the public stash payload when
// they see that query param, so anonymous viewers can read the item without
// workspace membership. Without this allowance the layout redirects to
// /login before the viewer's stash-fallback can kick in.
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user, loading, logout } = useAuth();
  const isWorkspaceStashRoute =
    pathname.startsWith("/workspaces/") && searchParams.has("stash");
  const isPublicCartridgeRoute =
    pathname.startsWith("/cartridges/") ||
    pathname.startsWith("/session-folders/") ||
    isWorkspaceStashRoute;

  useEffect(() => {
    if (loading) return;
    if (user) return;
    if (isPublicCartridgeRoute) return;
    router.push("/login");
  }, [user, loading, isPublicCartridgeRoute, router]);

  if (loading) {
    return isPublicCartridgeRoute ? <PublicCartridgeSkeleton /> : <AppShellSkeleton />;
  }

  if (isWorkspaceStashRoute) {
    return <main className="min-h-screen bg-background">{children}</main>;
  }

  if (!user) {
    if (isPublicCartridgeRoute) {
      return <main className="min-h-screen bg-background">{children}</main>;
    }
    return null;
  }

  return (
    <AppShell user={user} onLogout={logout}>
      {children}
    </AppShell>
  );
}
