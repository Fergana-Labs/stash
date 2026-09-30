"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/hooks/useAuth";

export default function RewardModelsLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading || !user) return null;
  if (!user.reward_models_enabled) {
    return <p className="p-8 text-sm text-muted-foreground">Reward models are not enabled for this account.</p>;
  }
  return children;
}
