"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import WorkspaceFileBrowser from "../../../../../components/workspace/file-browser/WorkspaceFileBrowser";
import { useAuth } from "../../../../../hooks/useAuth";
import { getFolderContents } from "../../../../../lib/api";

export default function FolderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const folderId = params.folderId as string;
  const { user, loading } = useAuth();

  // Small auxiliary breadcrumb fetch so the top bar is correct before the
  // file browser shell finishes its own load. The shell still owns the main
  // folder-contents fetch.
  const [crumbs, setCrumbs] = useState<{ label: string; href?: string }[]>([
    { label: "Folder" },
  ]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    getFolderContents(workspaceId, folderId)
      .then((c) => {
        if (cancelled) return;
        const trail = c.breadcrumbs.slice(0, -1).map((cr) => ({
          label: cr.name,
          href: `/workspaces/${workspaceId}/folders/${cr.id}`,
        }));
        setCrumbs([
          { label: "Files", href: `/workspaces/${workspaceId}/files` },
          ...trail,
          { label: c.folder.name },
        ]);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user, workspaceId, folderId]);

  useBreadcrumbs(
    crumbs,
    `${workspaceId}/files/${folderId}/${crumbs.map((c) => c.label).join("/")}`
  );

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return <WorkspaceFileBrowser workspaceId={workspaceId} folderId={folderId} />;
}
