"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ReactNode, useEffect } from "react";

import WorkspaceShell from "@/components/workspace/workspace-shell";
import ImportProgressPill from "@/components/ImportProgressPill";
import {
  AppShellSkeleton,
  PublicSkillSkeleton,
} from "@/components/SkeletonStates";
import { useAuth } from "@/hooks/useAuth";

// Shared chrome for the signed-in app. Hosting AppShell here (rather than
// inside each subtree's layout or page) keeps the sidebar mounted as you move
// between /skills/[slug] and the item viewers, so scroll position and
// folder-open state survive the navigation. Public skill routes are
// readable when signed out, so we render their children bare in that case.
//
// An item deep link with `?skill=<slug>` is also a public-skill route:
// the page/session/file viewers fall back to the public skill payload when
// they see that query param, so anonymous viewers can read the item without
// being signed in. Without this allowance the layout redirects to /login
// before the viewer's skill-fallback can kick in.
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user, loading, logout } = useAuth();
  const isSkillItemRoute = searchParams.has("skill");
  // Page and file viewers may hold content with an "anyone with the link"
  // public grant, so anonymous visitors must reach the viewer instead of being
  // bounced to /login; the viewer's own read (getPage/getFile) is the gate and
  // shows an error if the link isn't actually public.
  const isPublicSkillRoute =
    pathname.startsWith("/skills/") ||
    pathname.startsWith("/session-folders/") ||
    pathname.startsWith("/p/") ||
    pathname.startsWith("/f/") ||
    isSkillItemRoute;

  useEffect(() => {
    if (loading) return;
    if (user) return;
    if (isPublicSkillRoute) return;
    router.push("/login");
  }, [user, loading, isPublicSkillRoute, router]);

  if (loading) {
    return isPublicSkillRoute ? <PublicSkillSkeleton /> : <AppShellSkeleton />;
  }

  if (isSkillItemRoute) {
    return <main className="min-h-screen bg-background">{children}</main>;
  }

  if (!user) {
    if (isPublicSkillRoute) {
      return <main className="min-h-screen bg-background">{children}</main>;
    }
    return null;
  }

  return (
    <WorkspaceShell user={user} onLogout={logout}>
      {children}
      <ImportProgressPill />
    </WorkspaceShell>
  );
}
