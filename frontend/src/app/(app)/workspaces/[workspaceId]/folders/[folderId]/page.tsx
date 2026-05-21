"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useBreadcrumbs } from "../../../../../../components/BreadcrumbContext";
import { FileBrowserSkeleton } from "../../../../../../components/SkeletonStates";
import WorkspaceFileBrowser from "../../../../../../components/workspace/file-browser/WorkspaceFileBrowser";
import { useAuth } from "../../../../../../hooks/useAuth";
import {
  ApiError,
  getFolderContents,
  getPublicStash,
  type PublicStashItem,
  type WorkspaceStash,
} from "../../../../../../lib/api";
import { FolderBody } from "../../../../stashes/[slug]/StashItemBodies";

export default function FolderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = params.workspaceId as string;
  const folderId = params.folderId as string;
  const { user, loading } = useAuth();
  const stashSlug = searchParams.get("stash");

  // Small auxiliary breadcrumb fetch so the top bar is correct before the
  // file browser shell finishes its own load. The shell still owns the main
  // folder-contents fetch.
  const [crumbs, setCrumbs] = useState<{ label: string; href?: string }[]>([
    { label: "Folder" },
  ]);
  const [stashFallback, setStashFallback] = useState<
    { stash: WorkspaceStash; item: PublicStashItem } | null
  >(null);
  const [error, setError] = useState("");

  const loadStashFallback = useCallback(async () => {
    if (!stashSlug) return false;
    try {
      const data = await getPublicStash(stashSlug);
      const item = data.items.find(
        (it) => it.object_type === "folder" && it.object_id === folderId,
      );
      if (!item) {
        setError("This folder isn't part of the linked Stash.");
        return false;
      }
      setStashFallback({ stash: data.stash, item });
      setError("");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stash not found");
      return false;
    }
  }, [stashSlug, folderId]);

  useEffect(() => {
    if (!user) {
      if (!loading && stashSlug) void loadStashFallback();
      return;
    }
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
        setStashFallback(null);
      })
      .catch(async (e) => {
        if (cancelled) return;
        if (
          stashSlug &&
          e instanceof ApiError &&
          (e.status === 401 || e.status === 403 || e.status === 404)
        ) {
          await loadStashFallback();
        }
      });
    return () => {
      cancelled = true;
    };
  }, [user, loading, workspaceId, folderId, stashSlug, loadStashFallback]);

  useBreadcrumbs(
    crumbs,
    `${workspaceId}/files/${folderId}/${crumbs.map((c) => c.label).join("/")}`
  );

  useEffect(() => {
    if (!loading && !user && !stashSlug) router.push("/login");
  }, [user, loading, router, stashSlug]);

  if (loading) return <FileBrowserSkeleton />;
  if (stashFallback) {
    return (
      <StashFallbackFolderView
        stashSlug={stashSlug ?? ""}
        stashTitle={stashFallback.stash.title}
        item={stashFallback.item}
      />
    );
  }
  if (!user) {
    if (!stashSlug) return null;
    if (!error) return <FileBrowserSkeleton />;
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="font-display text-[24px] font-bold text-foreground">Folder unavailable</h1>
        <p className="mt-2 text-[14px] leading-relaxed text-dim">{error}</p>
      </div>
    );
  }

  return <WorkspaceFileBrowser workspaceId={workspaceId} folderId={folderId} />;
}

function StashFallbackFolderView({
  stashSlug,
  stashTitle,
  item,
}: {
  stashSlug: string;
  stashTitle: string;
  item: PublicStashItem;
}) {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <Link
          href={`/stashes/${stashSlug}`}
          className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-foreground"
        >
          ← {stashTitle}
        </Link>
        <h1 className="mt-3 m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.015em] text-foreground">
          {item.label || "(untitled folder)"}
        </h1>
        <div className="mt-1 text-[11.5px] uppercase tracking-wide text-muted">
          folder · read-only via Stash
        </div>
        <div className="mt-6">
          <FolderBody item={item} />
        </div>
      </div>
    </div>
  );
}
