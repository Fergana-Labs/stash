"use client";

import { useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import AppShell from "../../../components/AppShell";
import { useAuth } from "../../../hooks/useAuth";

export default function StashLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      {children}
    </AppShell>
  );
}
