"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Wrench } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useAuth } from "@/hooks/useAuth";

export default function ToolsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useBreadcrumbs([{ label: "Tools" }], "tools");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading || !user) return null;

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-muted-foreground">
      <Wrench className="h-8 w-8" />
      <div>
        <h1 className="text-base font-semibold text-foreground">Tools</h1>
        <p className="mt-1 text-sm">Connect MCP servers and custom tools here — coming soon.</p>
      </div>
    </div>
  );
}
