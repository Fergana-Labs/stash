"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import FilesExplorer from "@/components/workspace/files-explorer";
import { useAuth } from "@/hooks/useAuth";

export default function FilesPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useBreadcrumbs([{ label: "Files" }], "files");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading) return <FileBrowserSkeleton />;
  if (!user) return null;

  return <FilesExplorer onRoot={() => {}} rootLabel="Files" rootFolderId={null} />;
}
