"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useProductCheckpoint } from "@/components/ProductCheckpointContext";

export default function RewardModelsLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const checkpoint = useProductCheckpoint();
  const pathname = usePathname();
  const router = useRouter();
  const unavailable = checkpoint === "floodgate-2026-10-05"
    && /^\/reward-models\/(review|changes|graders|optimization)(\/|$)/.test(pathname);
  useEffect(() => {
    if (unavailable) router.replace("/reward-models");
  }, [unavailable, router]);
  if (loading || !user) return null;
  if (!user.reward_models_enabled) {
    return <p className="p-8 text-sm text-muted-foreground">Reward models are not enabled for this account.</p>;
  }
  if (unavailable) return null;
  return children;
}
