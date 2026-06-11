"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "../../../../../../components/BreadcrumbContext";
import { useShareAction } from "../../../../../../components/ShellChromeContext";
import { FileBrowserSkeleton } from "../../../../../../components/SkeletonStates";
import ResourceShareButton from "../../../../../../components/share/ResourceShareButton";
import WorkspaceFileBrowser from "../../../../../../components/workspace/file-browser/WorkspaceFileBrowser";
import { useAuth } from "../../../../../../hooks/useAuth";
import {
  ApiError,
  getFolderContents,
  getPublicCartridge,
  type FolderContents,
  type PublicCartridgeItem,
  type WorkspaceCartridge,
} from "../../../../../../lib/api";
import { FolderBody } from "../../../../cartridges/[slug]/CartridgeItemBodies";

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
  const [folderName, setFolderName] = useState<string | null>(null);
  // Anonymous viewer reading a publicly-shared folder (anyone with the link).
  const [publicContents, setPublicContents] = useState<FolderContents | null>(null);
  const [stashFallback, setStashFallback] = useState<
    { stash: WorkspaceCartridge; item: PublicCartridgeItem } | null
  >(null);
  const [error, setError] = useState("");

  const loadStashFallback = useCallback(async () => {
    if (!stashSlug) return false;
    try {
      const data = await getPublicCartridge(stashSlug);
      const item = data.items.find(
        (it) => it.object_type === "folder" && it.object_id === folderId,
      );
      if (!item) {
        setError("This folder isn't part of the linked Stash.");
        return false;
      }
      setStashFallback({ stash: data.cartridge, item });
      setError("");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stash not found");
      return false;
    }
  }, [stashSlug, folderId]);

  // Anonymous viewer, no stash hint: the folder may carry a public (anyone
  // with the link) grant. The contents endpoint allows anonymous viewers and
  // filters children to publicly-readable rows.
  const loadPublic = useCallback(async () => {
    try {
      const contents = await getFolderContents(workspaceId, folderId);
      setPublicContents(contents);
      setFolderName(contents.folder.name);
      setCrumbs([{ label: contents.folder.name }]);
    } catch {
      router.push("/login");
    }
  }, [workspaceId, folderId, router]);

  useEffect(() => {
    if (!user) {
      if (loading) return;
      if (stashSlug) void loadStashFallback();
      else void loadPublic();
      return;
    }
    let cancelled = false;
    setFolderName(null);
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
        setFolderName(c.folder.name);
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
  }, [user, loading, workspaceId, folderId, stashSlug, loadStashFallback, loadPublic]);

  useBreadcrumbs(
    crumbs,
    `${workspaceId}/files/${folderId}/${crumbs.map((c) => c.label).join("/")}`
  );

  const shareAction = useMemo(() => {
    if (!folderName || stashSlug || !user) return null;
    return (
      <ResourceShareButton
        objectType="folder"
        objectId={folderId}
        resourceName={folderName}
        resourceUrlPath={`/workspaces/${workspaceId}/folders/${folderId}`}
        currentUser={user}
      />
    );
  }, [folderId, folderName, stashSlug, user, workspaceId]);
  useShareAction(shareAction);

  if (loading) return <FileBrowserSkeleton />;
  if (!user && publicContents) {
    return <PublicFolderView contents={publicContents} />;
  }
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
    if (!stashSlug) return <FileBrowserSkeleton />;
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
  item: PublicCartridgeItem;
}) {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <Link
          href={`/cartridges/${stashSlug}`}
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

function PublicFolderView({ contents }: { contents: FolderContents }) {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <h1 className="m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.015em] text-foreground">
          {contents.folder.name}
        </h1>
        <div className="mt-1 text-[11.5px] uppercase tracking-wide text-muted">
          folder · shared with link
        </div>
        <ul className="mt-6 flex flex-col gap-1">
          {contents.pages.map((page) => (
            <li key={page.id}>
              <Link
                href={`/p/${page.id}`}
                className="block rounded-md px-3 py-2 text-[13.5px] text-foreground hover:bg-raised"
              >
                {page.name}
              </Link>
            </li>
          ))}
          {contents.files.map((file) => (
            <li key={file.id}>
              <Link
                href={`/f/${file.id}`}
                className="block rounded-md px-3 py-2 text-[13.5px] text-foreground hover:bg-raised"
              >
                {file.name}
              </Link>
            </li>
          ))}
          {contents.tables.map((table) => (
            <li key={table.id}>
              <Link
                href={`/tables/${table.id}`}
                className="block rounded-md px-3 py-2 text-[13.5px] text-foreground hover:bg-raised"
              >
                {table.name}
              </Link>
            </li>
          ))}
          {contents.pages.length + contents.files.length + contents.tables.length === 0 && (
            <li className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
              This folder is empty.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
