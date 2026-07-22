"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { useShareAction } from "@/components/ShellChromeContext";
import { recordRecent } from "@/lib/pins";
import { FileViewerSkeleton } from "@/components/SkeletonStates";
import { useAuth } from "@/hooks/useAuth";
import {
  ApiError,
  getFile,
  getFolderContents,
  getPublicSkill,
  ingestCsvFile,
  ingestXlsxFile,
  trashItem,
  updateFile,
  type FolderBreadcrumb,
} from "@/lib/api";
import { findInSkillContents, skillItemPath } from "@/lib/localSkill";
import { routes } from "@/lib/workspace-routes";
import type { FileInfo } from "@/lib/types";
import FileContentRenderer, {
  isImage,
  isMarkdown,
  isPdf,
  isText,
} from "@/components/content/FileContentRenderer";
import FileViewerHeader from "@/components/content/FileViewerHeader";
import { sectionCrumbs, useMemoryFolderId } from "@/lib/memory-folder";
import ResourceShareButton from "@/components/share/ResourceShareButton";

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

export default function FileViewerPage({ fileId }: { fileId: string }) {
  return (
    <Suspense fallback={<FileViewerSkeleton />}>
      <FileViewerPageInner fileId={fileId} />
    </Suspense>
  );
}

function FileViewerPageInner({ fileId }: { fileId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const confirm = useConfirm();
  // ?skill=<slug> is a back-link hint AND a permission fallback. We try the
  // owner's file endpoint first so the owner gets the full editor chrome
  // (rename / move / trash / CSV ingest). Others fall back to the
  // public-skill payload, read-only.
  const skillSlug = searchParams.get("skill");
  const { user, loading, logout: _logout } = useAuth();
  // logout isn't used here; kept for parity with other app pages.
  void _logout;

  const [file, setFile] = useState<FileInfo | null>(null);
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
  const [error, setError] = useState("");
  const [skillTitle, setSkillTitle] = useState<string | null>(null);
  // readOnly flips on only when we fall back to the skill payload — i.e.
  // the viewer can't reach the owner's file endpoint. The owner who arrives
  // via ?skill= still gets full edit affordances.
  const [readOnly, setReadOnly] = useState(false);

  const memoryFolderId = useMemoryFolderId();
  const ancestorCrumbs = useMemo(
    () =>
      readOnly
        ? [
            { label: "Skills", href: "/skills" },
            { label: skillTitle ?? "Skill", href: skillSlug ? `/skills/${skillSlug}` : "/skills" },
          ]
        : sectionCrumbs(folderChain, memoryFolderId),
    [readOnly, skillTitle, skillSlug, folderChain, memoryFolderId],
  );

  useBreadcrumbs(
    [...ancestorCrumbs, { label: file ? file.name : "File" }],
    `file/${fileId}/${file?.name ?? ""}/${folderChain.map((c) => c.id).join(",")}/${skillSlug ?? ""}`
  );

  const loadSkillFallback = useCallback(async () => {
    if (!skillSlug) return false;
    try {
      const skill = await getPublicSkill(skillSlug);
      setSkillTitle(skill.skill.title);
      const item = findInSkillContents(skill.contents, "file", fileId);
      if (!item) {
        setError("File isn't in this Skill.");
        return false;
      }
      const synth: FileInfo = {
        id: fileId,
        owner_user_id: skill.skill.owner_user_id,
        folder_id: null,
        name: item.name,
        content_type: item.content_type ?? "",
        size_bytes: item.size_bytes ?? 0,
        url: item.url ?? "",
        app_url: skillItemPath("file", fileId, skillSlug),
        uploaded_by: "",
        created_at: item.created_at ?? "",
      };
      setFile(synth);
      setFolderChain([]);
      setReadOnly(true);
      setError("");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Skill not found");
      return false;
    }
  }, [skillSlug, fileId]);

  const load = useCallback(async () => {
    try {
      const f = await getFile(fileId);
      setFile(f);
      setReadOnly(false);
      recordRecent(fileId, "file");
      if (f.folder_id) {
        try {
          const contents = await getFolderContents(f.folder_id);
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
          router.replace(routes.table(f.linked_table_id));
        } else {
          try {
            const table = await ingestCsvFile(fileId);
            router.replace(routes.table(table.id));
          } catch (e) {
            setError(e instanceof Error ? e.message : "CSV ingest failed");
          }
        }
        return;
      }
      // XLSX: same shape, but one table per sheet. Redirect to the first
      // sheet's table; the others appear in the sidebar.
      if (isXlsx(f.content_type, f.name)) {
        if (f.linked_table_id) {
          router.replace(routes.table(f.linked_table_id));
        } else {
          try {
            const { tables } = await ingestXlsxFile(fileId);
            if (tables.length === 0) {
              setError("Workbook had no readable sheets");
            } else {
              router.replace(routes.table(tables[0].id));
            }
          } catch (e) {
            setError(e instanceof Error ? e.message : "XLSX ingest failed");
          }
        }
        return;
      }
    } catch (e) {
      if (
        skillSlug &&
        e instanceof ApiError &&
        (e.status === 401 || e.status === 403 || e.status === 404)
      ) {
        if (await loadSkillFallback()) return;
      }
      setError(e instanceof Error ? e.message : "Failed to load file");
    }
  }, [fileId, router, skillSlug, loadSkillFallback]);

  useEffect(() => {
    if (user) load();
    else if (!loading && skillSlug) void loadSkillFallback();
  }, [user, loading, load, loadSkillFallback, skillSlug]);

  useEffect(() => {
    if (!loading && !user && !skillSlug) router.push("/login");
  }, [user, loading, router, skillSlug]);

  const shareAction = useMemo(() => {
    if (!file || readOnly || !user) return null;
    return (
      <ResourceShareButton
        objectType="file"
        objectId={file.id}
        resourceName={file.name}
        resourceUrlPath={routes.file(file.id)}
        currentUser={user}
      />
    );
  }, [file, readOnly, user]);
  useShareAction(shareAction);

  if (loading) return <FileViewerSkeleton />;
  if (!user && !skillSlug) return null;
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
  const uploader = file?.uploaded_by_display_name || file?.uploaded_by_name;
  const tags = file ? [{ label: fileKindLabel, tone: "muted" as const }] : undefined;
  const meta: string[] = [];
  if (file) meta.push(formatBytes(file.size_bytes));
  if (updatedAt) meta.push(`Uploaded ${updatedAt}${uploader ? ` by ${uploader}` : ""}`);

  return (
    <div className="scroll-thin flex flex-1 min-h-0 flex-col overflow-hidden">
      <div className="flex-1 overflow-auto bg-base scroll-thin">
        <FileViewerHeader
          icon={<KindGlyph contentType={file?.content_type ?? ""} name={file?.name ?? ""} />}
          iconColor={kindIconColor(file?.content_type ?? "")}
          breadcrumbs={ancestorCrumbs}
          title={file?.name ?? "File"}
          onRenameTitle={
            file
              ? async (next) => {
                  const updated = await updateFile(file.id, { name: next });
                  setFile(updated);
                  return updated.name;
                }
              : undefined
          }
          readOnly={readOnly}
          readOnlyLabel="read-only · via Skill"
          backLink={readOnly && skillSlug ? { label: skillTitle ?? "Skill", href: `/skills/${skillSlug}` } : undefined}
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
                            const ok = await confirm({
                              title: `Move "${file.name}" to trash?`,
                              confirmLabel: "Move to trash",
                            });
                            if (!ok) return;
                            try {
                              await trashItem("file", fileId);
                              router.push("/");
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
