"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import WorkspaceShell from "@/components/workspace/workspace-shell";
import { TableEditorSkeleton } from "@/components/SkeletonStates";
import { useAuth } from "@/hooks/useAuth";
import TableClient from "./TableClient";

export default function TableRouteClient({ tableId }: { tableId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading, logout } = useAuth();
  const skillSlug = searchParams.get("skill");

  useEffect(() => {
    if (!loading && !user && !skillSlug) router.push("/login");
  }, [user, loading, skillSlug, router]);

  if (skillSlug) return <TableClient tableId={tableId} />;
  if (loading) return <TableEditorSkeleton />;
  if (!user) return null;

  return (
    <WorkspaceShell user={user} onLogout={logout}>
      {null}
    </WorkspaceShell>
  );
}
