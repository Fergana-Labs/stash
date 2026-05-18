"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import WorkspaceFileBrowser from "../../../../components/workspace/file-browser/WorkspaceFileBrowser";
import { useAuth } from "../../../../hooks/useAuth";

export default function WorkspaceFilesPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();

  useBreadcrumbs([{ label: "Files" }], `${workspaceId}/files`);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return <WorkspaceFileBrowser workspaceId={workspaceId} folderId={null} />;
}
