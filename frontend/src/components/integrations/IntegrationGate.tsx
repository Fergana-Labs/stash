"use client";

import type { ReactNode } from "react";
import DeveloperGate from "@/components/developer/DeveloperGate";
import { useAuth } from "@/hooks/useAuth";
import { showPersonalIntegrations } from "@/lib/flags";
import { useScope } from "@/lib/scope-store";

export default function IntegrationGate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const scope = useScope();

  if (loading) return null;
  if (showPersonalIntegrations(user) && scope?.view !== "developer") return children;
  return <DeveloperGate>{children}</DeveloperGate>;
}
