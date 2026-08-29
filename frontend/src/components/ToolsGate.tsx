"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { showTools } from "@/lib/flags";

// Tools is hidden from the rail for most users (see lib/flags.ts); this keeps
// the routes themselves from being reachable by URL.
export default function ToolsGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, loading } = useAuth();
  const allowed = showTools(user);

  useEffect(() => {
    if (!loading && user && !allowed) router.replace("/");
  }, [loading, user, allowed, router]);

  if (!user || !allowed) return null;
  return <>{children}</>;
}
