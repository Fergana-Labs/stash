"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import UploadedFilesList from "@/components/workspace/uploaded-files-list";
import { useAuth } from "@/hooks/useAuth";

export default function FilesPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading) return <FileBrowserSkeleton />;
  if (!user) return null;

  return <UploadedFilesList />;
}
