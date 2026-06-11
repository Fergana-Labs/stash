"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import {
  useActiveWorkspaceId,
  useShareAction,
} from "../../../../components/ShellChromeContext";
import { recordRecent } from "../../../../lib/pins";
import { FileViewerSkeleton } from "../../../../components/SkeletonStates";
import { useAuth } from "../../../../hooks/useAuth";
import {
  ApiError,
  getFile,
  getFolderContents,
  getPublicCartridge,
  ingestCsvFile,
  ingestXlsxFile,
  trashItem,
  updateFile,
  type FolderBreadcrumb,
} from "../../../../lib/api";
import type { FileInfo } from "../../../../lib/types";
import FileContentRenderer, {
  isImage,
  isMarkdown,
  isPdf,
  isText,
} from "../../../../components/workspace/FileContentRenderer";
import FileViewerHeader from "../../../../components/workspace/FileViewerHeader";
import FileShareButton from "../../../../components/share/FileShareButton";

function isCsv(ct: string) {
  return ct?.includes("csv") || ct === "text/csv";
}

const XLSX_CONTENT_TYPES = new Set([
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
]);

function isXlsx(ct: string, name: string) {
  return XLSX_CONTENT_TYPES.has(ct) || /\.xlsx?$/i.test(name);
}

export default function FileViewerPage() {
  return (
    <Suspense fallback={<FileViewerSkeleton />}>
      <FileViewerPageInner />
    </Suspense>
  );
}

function FileViewerPageInner() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const fileId = params.fileId as string;
  // ?stash=<slug> is a back-link hint AND a permission fallback. We try
  // the workspace endpoint first so workspace members get the full editor
  // chrome (rename / move / trash / CSV ingest). Non-members fall back to
  // the public-stash payload, read-only.
  const stashSlug = searchParams.get("stash");
  const { user, loading, logout: _logout } = useAuth();
  // logout isn't used here; kept for parity with other workspace pages.
  void _logout;

  const [file, setFile] = useState<FileInfo | null>(null);
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
  const [error, setError] = useState("");
  const [stashTitle, setStashTitle] = useState<string | null>(null);
  // readOnly flips on only when we fall back to the stash payload — i.e.
  // the viewer can't reach the workspace endpoint. Workspace members who
  // arrive via ?stash= still get full edit affordances.
  const [readOnly, setReadOnly] = useState(false);
  // Empty until the file loads — every consumer below renders or fires
  // only after that.
  const workspaceId = file?.workspace_id ?? "";
  useActiveWorkspaceId(workspaceId || null);

  useBreadcrumbs(
    readOnly
      ? [
          { label: "Cartridges", href: "/cartridges" },
          { label: stashTitle ?? "Cartridge", href: stashSlug ? `/cartridges/${stashSlug}` : "/cartridges" },
          { label: file ? file.name : "File" },
        ]
      : [
          ...folderChain.map((c) => ({
            label: c.name,
            href: `/workspaces/${workspaceId}/folders/${c.id}`,
          })),
          { label: file ? file.name : "File" },
        ],
    `${workspaceId}/file/${fileId}/${file?.name ?? ""}/${folderChain.map((c) => c.id).join(",")}/${stashSlug ?? ""}`
  );

  const loadStashFallback = useCallback(async () => {
    if (!stashSlug) return false;
    try {
      const stash = await getPublicCartridge(stashSlug);
      setStashTitle(stash.cartridge.title);
      const item = stash.items.find(
        (it) => it.object_type === "file" && it.object_id === fileId
      );
      if (!item || !item.inline) {
        setError("File isn't in this Stash.");
        return false;
      }
      const inline = item.inline as {
        name?: string;
        content_type?: string;
        size_bytes?: number;
        url?: string;
        created_at?: string;
      };
      const synth: FileInfo = {
        id: fileId,
        workspace_id: stash.cartridge.workspace_id,
        folder_id: null,
        name: inline.name ?? item.label,
        content_type: inline.content_type ?? "",
        size_bytes: inline.size_bytes ?? 0,
        url: inline.url ?? "",
        app_url: `/f/${fileId}?stash=${stashSlug}`,
        uploaded_by: "",
        created_at: inline.created_at ?? "",
      };
      setFile(synth);
      setFolderChain([]);
      setReadOnly(true);
      setError("");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stash not found");
      return false;
    }
  }, [stashSlug, fileId]);

  const load = useCallback(async () => {
    try {
      const f = await getFile(fileId);
      // The canonical endpoint 404s workspace-less rows, so ws is always set
      // here; the guard narrows the nullable type.
      const ws = f.workspace_id ?? "";
      setFile(f);
      setReadOnly(false);
      recordRecent(ws, fileId, "file");
      if (f.folder_id) {
        try {
          const contents = await getFolderContents(ws, f.folder_id);
          setFolderChain(contents.breadcrumbs);
        } catch {
          setFolderChain([]);
        }
      } else {
        setFolderChain([]);
      }

      // CSVs always live in /tables/[id]. If already linked, redirect.
      // Otherwise ingest and then redirect — user never sees this route for CSVs.
      if (isCsv(f.content_type)) {
        if (f.linked_table_id) {
          router.replace(`/tables/${f.linked_table_id}`);
        } else {
          try {
            const table = await ingestCsvFile(ws, fileId);
            router.replace(`/tables/${table.id}`);
          } catch (e) {
            setError(e instanceof Error ? e.message : "CSV ingest failed");
          }
        }
        return;
      }
      // XLSX: same shape, but one table per sheet. Redirect to the first
      // sheet's table; the others appear in the workspace sidebar.
      if (isXlsx(f.content_type, f.name)) {
        if (f.linked_table_id) {
          router.replace(`/tables/${f.linked_table_id}`);
        } else {
          try {
            const { tables } = await ingestXlsxFile(ws, fileId);
            if (tables.length === 0) {
              setError("Workbook had no readable sheets");
            } else {
              router.replace(`/tables/${tables[0].id}`);
            }
          } catch (e) {
            setError(e instanceof Error ? e.message : "XLSX ingest failed");
          }
        }
        return;
      }
    } catch (e) {
      if (
        stashSlug &&
        e instanceof ApiError &&
        (e.status === 401 || e.status === 403 || e.status === 404)
      ) {
        if (await loadStashFallback()) return;
      }
      setError(e instanceof Error ? e.message : "Failed to load file");
    }
  }, [fileId, router, stashSlug, loadStashFallback]);

  useEffect(() => {
    if (user) load();
    else if (!loading && stashSlug) void loadStashFallback();
  }, [user, loading, load, loadStashFallback, stashSlug]);

  useEffect(() => {
    if (!loading && !user && !stashSlug) router.push("/login");
  }, [user, loading, router, stashSlug]);

  const shareAction = useMemo(() => {
    if (!file || readOnly || !user) return null;
    return (
      <FileShareButton
        fileId={file.id}
        fileName={file.name}
        currentUser={user}
      />
    );
  }, [file, readOnly, user]);
  useShareAction(shareAction);

  if (loading) return <FileViewerSkeleton />;
  if (!user && !stashSlug) return null;
  if (!file && !error) return <FileViewerSkeleton />;

  const fileKindLabel = file ? kindLabel(file.content_type, file.name) : "";
  const updatedAt = file?.created_at
    ? new Date(file.created_at).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;
  const tags = file ? [{ label: fileKindLabel, tone: "muted" as const }] : undefined;
  const meta: string[] = [];
  if (file) meta.push(formatBytes(file.size_bytes));
  if (updatedAt) meta.push(`Uploaded ${updatedAt}`);

  return (
    <div className="scroll-thin flex flex-1 min-h-0 flex-col overflow-hidden">
      <div className="flex-1 overflow-auto bg-base scroll-thin">
        <FileViewerHeader
          icon={<KindGlyph contentType={file?.content_type ?? ""} name={file?.name ?? ""} />}
          iconColor={kindIconColor(file?.content_type ?? "")}
          title={file?.name ?? "File"}
          onRenameTitle={
            file
              ? async (next) => {
                  const updated = await updateFile(workspaceId, file.id, { name: next });
                  setFile(updated);
                  return updated.name;
                }
              : undefined
          }
          readOnly={readOnly}
          readOnlyLabel="read-only · via Stash"
          backLink={readOnly && stashSlug ? { label: stashTitle ?? "Stash", href: `/cartridges/${stashSlug}` } : undefined}
          tags={tags}
          meta={meta}
          downloadOptions={
            file?.url
              ? [
                  { label: "Download", onSelect: () => triggerDownload(file.url, file.name) },
                  ...(readOnly
                    ? []
                    : [
                        {
                          label: "Delete",
                          destructive: true,
                          onSelect: async () => {
                            if (!window.confirm(`Move "${file.name}" to trash?`)) return;
                            try {
                              await trashItem(workspaceId, "file", fileId);
                              router.push(`/workspaces/${workspaceId}`);
                            } catch (e) {
                              setError(e instanceof Error ? e.message : "Delete failed");
                            }
                          },
                        },
                      ]),
                ]
              : undefined
          }
        />

        {error && (
          <div className="border-b border-red-300/40 bg-red-500/10 px-5 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {file && (
          <FileContentRenderer
            url={file.url}
            name={file.name}
            contentType={file.content_type}
          />
        )}
      </div>
    </div>
  );
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function kindLabel(contentType: string, name: string): string {
  if (isPdf(contentType)) return "pdf";
  if (isImage(contentType)) return "image";
  if (isMarkdown(contentType, name)) return "markdown";
  if (isText(contentType)) return "text";
  return "file";
}

function kindIconColor(contentType: string): string {
  if (isPdf(contentType)) return "#E11D48";
  if (isImage(contentType)) return "#EA580C";
  return "var(--text-muted)";
}

function triggerDownload(url: string, name: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function KindGlyph({ contentType, name }: { contentType: string; name: string }) {
  if (isPdf(contentType)) {
    return (
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
        <path d="M14 3v5h5" />
        <path d="M9 14h6" />
        <path d="M9 17h3" />
      </svg>
    );
  }
  if (isImage(contentType)) {
    return (
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <circle cx="9" cy="9.5" r="1.4" />
        <path d="M21 16l-5-5-9 9" />
      </svg>
    );
  }
  if (isMarkdown(contentType, name)) {
    return (
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
        <path d="M14 3v5h5" />
        <path d="M9 13h6M9 17h4" />
      </svg>
    );
  }
  // generic file
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}
