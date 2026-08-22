"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { showToolsAndChat } from "@/lib/flags";

// Tools and Chat are hidden from the rail for most users (see lib/flags.ts);
// this keeps the routes themselves from being reachable by URL.
export default function ToolsAndChatGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, loading } = useAuth();
  const allowed = showToolsAndChat(user);

  useEffect(() => {
    if (!loading && user && !allowed) router.replace("/");
  }, [loading, user, allowed, router]);

  if (!user || !allowed) return null;
  return <>{children}</>;
}
