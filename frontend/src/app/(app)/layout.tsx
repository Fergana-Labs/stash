"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ReactNode, useEffect } from "react";

import AppShell from "../../components/AppShell";
import {
  AppShellSkeleton,
  PublicSkillSkeleton,
} from "../../components/SkeletonStates";
import { useAuth } from "../../hooks/useAuth";

// Shared chrome for the signed-in app. Hosting AppShell here (rather than
// inside each subtree's layout or page) keeps the sidebar mounted as you move
// between /skills/[slug] and /workspaces/[workspaceId], so scroll position
// and folder-open state survive the navigation. Public skill routes are
// readable when signed out, so we render their children bare in that case.
//
// A workspace deep link with `?skill=<slug>` is also a public-skill route:
// the page/session/file viewers fall back to the public skill payload when
// they see that query param, so anonymous viewers can read the item without
// workspace membership. Without this allowance the layout redirects to
// /login before the viewer's skill-fallback can kick in.
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user, loading, logout } = useAuth();
  const isWorkspaceSkillRoute =
    pathname.startsWith("/workspaces/") && searchParams.has("skill");
  // Resource detail routes may carry a public (anyone with the link) grant.
  // Their clients probe it themselves and bounce to /login when it's absent,
  // so the layout must not pre-empt them for anonymous viewers.
  const isResourceDetailRoute =
    pathname.startsWith("/p/") ||
    pathname.startsWith("/f/") ||
    pathname.startsWith("/sessions/") ||
    /^\/workspaces\/[^/]+\/folders\//.test(pathname);
  const isPublicSkillRoute =
    pathname.startsWith("/skills/") ||
    pathname.startsWith("/session-folders/") ||
    isWorkspaceSkillRoute ||
    isResourceDetailRoute;

  useEffect(() => {
    if (loading) return;
    if (user) return;
    if (isPublicSkillRoute) return;
    router.push("/login");
  }, [user, loading, isPublicSkillRoute, router]);

  if (loading) {
    return isPublicSkillRoute ? <PublicSkillSkeleton /> : <AppShellSkeleton />;
  }

  if (isWorkspaceSkillRoute) {
    return <main className="min-h-screen bg-background">{children}</main>;
  }

  if (!user) {
    if (isPublicSkillRoute) {
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
