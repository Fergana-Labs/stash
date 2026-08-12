"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import VfsBrowser from "@/components/content/vfs-browser/VfsBrowser";
import { useAuth } from "@/hooks/useAuth";

export default function VfsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useBreadcrumbs([{ label: "VFS", href: "/files" }], "files");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading) return <FileBrowserSkeleton />;
  if (!user) return null;

  return <VfsBrowser />;
}
