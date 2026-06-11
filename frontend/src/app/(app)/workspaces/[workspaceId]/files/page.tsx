"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { FileBrowserSkeleton } from "../../../../../components/SkeletonStates";
import WorkspaceFileBrowser from "../../../../../components/workspace/file-browser/WorkspaceFileBrowser";
import { useAuth } from "../../../../../hooks/useAuth";

export default function WorkspaceFilesPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();

  useBreadcrumbs([{ label: "Drive" }], `${workspaceId}/files`);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading) return <FileBrowserSkeleton />;
  if (!user) return null;

  return <WorkspaceFileBrowser workspaceId={workspaceId} folderId={null} />;
}
