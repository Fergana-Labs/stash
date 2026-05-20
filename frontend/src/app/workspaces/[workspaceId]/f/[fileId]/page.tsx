"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import {
  DocumentBodySkeleton,
  FileViewerSkeleton,
  SkeletonBlock,
} from "../../../../../components/SkeletonStates";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  getFile,
  getFolderContents,
  getPublicStash,
  ingestCsvFile,
  trashItem,
  updateFile,
  type FolderBreadcrumb,
} from "../../../../../lib/api";
import type { FileInfo } from "../../../../../lib/types";
import FileViewerHeader from "../../../../../components/workspace/FileViewerHeader";

function isCsv(ct: string) {
  return ct?.includes("csv") || ct === "text/csv";
}
function isPdf(ct: string) {
  return ct?.includes("pdf");
}
function isImage(ct: string) {
  return ct?.startsWith("image/");
}
function isMarkdown(ct: string, name: string) {
  return ct?.includes("markdown") || name.toLowerCase().endsWith(".md");
}
function isText(ct: string) {
  return ct?.startsWith("text/");
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
  const workspaceId = params.workspaceId as string;
  const fileId = params.fileId as string;
  // When ?stash=<slug> is present, the viewer reads through the public
  // stash payload instead of the workspace endpoint. This lets non-members
  // of the owning workspace open files that the stash owner has shared,
  // with the stash's permission gate the only authorization check.
  const stashSlug = searchParams.get("stash");
  const readOnly = !!stashSlug;
  const { user, loading, logout: _logout } = useAuth();
  // logout isn't used here; kept for parity with other workspace pages.
  void _logout;

  const [file, setFile] = useState<FileInfo | null>(null);
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
  const [textBody, setTextBody] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [stashTitle, setStashTitle] = useState<string | null>(null);

  useBreadcrumbs(
    readOnly
      ? [
          { label: "Stashes", href: "/stashes" },
          { label: stashTitle ?? "Stash", href: stashSlug ? `/stashes/${stashSlug}` : "/stashes" },
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

  const load = useCallback(async () => {
    try {
      if (stashSlug) {
        // Stash-scoped read. The backend inlines the file's metadata + a
        // signed download URL when the stash is readable, so we synthesize
        // a FileInfo from that and skip the workspace endpoint entirely.
        const stash = await getPublicStash(stashSlug);
        setStashTitle(stash.stash.title);
        const item = stash.items.find(
          (it) => it.object_type === "file" && it.object_id === fileId
        );
        if (!item || !item.inline) {
          setError("File isn't in this Stash.");
          return;
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
          workspace_id: stash.stash.workspace_id,
          folder_id: null,
          name: inline.name ?? item.label,
          content_type: inline.content_type ?? "",
          size_bytes: inline.size_bytes ?? 0,
          url: inline.url ?? "",
          uploaded_by: "",
          created_at: inline.created_at ?? "",
        };
        setFile(synth);
        setFolderChain([]);
        if (synth.url && (isText(synth.content_type) || isMarkdown(synth.content_type, synth.name))) {
          const res = await fetch(synth.url);
          if (res.ok) setTextBody(await res.text());
        }
        return;
      }

      const f = await getFile(workspaceId, fileId);
      setFile(f);
      if (f.folder_id) {
        try {
          const contents = await getFolderContents(workspaceId, f.folder_id);
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
          router.replace(`/tables/${f.linked_table_id}?workspaceId=${workspaceId}`);
        } else {
          try {
            const table = await ingestCsvFile(workspaceId, fileId);
            router.replace(`/tables/${table.id}?workspaceId=${workspaceId}`);
          } catch (e) {
            setError(e instanceof Error ? e.message : "CSV ingest failed");
          }
        }
        return;
      }

      if (f.url && (isText(f.content_type) || isMarkdown(f.content_type, f.name))) {
        const res = await fetch(f.url);
        if (res.ok) setTextBody(await res.text());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load file");
    }
  }, [workspaceId, fileId, router, stashSlug]);

  useEffect(() => {
    // Stash mode is anonymous-readable, so load eagerly. Workspace mode
    // waits for the auth check before hitting the workspace endpoint.
    if (readOnly || user) load();
  }, [readOnly, user, load]);

  useEffect(() => {
    // Only redirect to login in workspace mode. Stash-scoped readers can
    // be anonymous when the stash is public.
    if (!readOnly && !loading && !user) router.push("/login");
  }, [readOnly, user, loading, router]);

  if (loading && !readOnly) return <FileViewerSkeleton />;
  if (!user && !readOnly) return null;
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
        backLink={readOnly && stashSlug ? { label: stashTitle ?? "Stash", href: `/stashes/${stashSlug}` } : undefined}
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

      <div className="flex-1 overflow-auto bg-base scroll-thin">
        {file && <FileBody file={file} text={textBody} />}
      </div>
    </div>
  );
}

function FileBody({ file, text }: { file: FileInfo; text: string | null }) {
  if (!file.url) return <p className="px-5 py-8 text-muted">No download URL.</p>;
  if (isPdf(file.content_type)) {
    return <iframe src={file.url} className="h-full w-full bg-gray-200" title={file.name} />;
  }
  if (isImage(file.content_type)) {
    return (
      <div className="flex items-center justify-center bg-gray-100 p-8">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={file.url} alt={file.name} className="max-h-full max-w-full" />
      </div>
    );
  }
  if (isMarkdown(file.content_type, file.name)) {
    if (text === null) return <DocumentBodySkeleton className="mx-auto mt-8 max-w-[920px]" />;
    return (
      <article className="prose prose-sm markdown-content mx-auto max-w-[920px] px-12 py-8 text-foreground">
        <Markdown remarkPlugins={[remarkGfm]}>{text || ""}</Markdown>
      </article>
    );
  }
  if (isText(file.content_type)) {
    if (text === null) {
      return (
        <div className="space-y-2 px-5 py-4">
          {[0, 1, 2, 3, 4, 5, 6, 7].map((row) => (
            <SkeletonBlock key={row} className="h-4 w-full max-w-4xl" />
          ))}
        </div>
      );
    }
    return (
      <pre className="scroll-thin h-full overflow-auto px-5 py-4 font-mono text-[12.5px] text-foreground">
        {text || ""}
      </pre>
    );
  }
  return (
    <div className="mx-auto max-w-md px-8 py-12 text-center text-[13px] text-muted">
      <p className="mb-3">No inline preview for this file type.</p>
      <a
        href={file.url}
        target="_blank"
        rel="noopener noreferrer"
        className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
      >
        Open original ↗
      </a>
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
  if (isImage(contentType)) return "#7C3AED";
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
