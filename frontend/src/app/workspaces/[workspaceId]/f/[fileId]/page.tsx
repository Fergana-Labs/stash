"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  getFile,
  getFolderContents,
  getPublicStash,
  ingestCsvFile,
  updateFile,
  type FolderBreadcrumb,
} from "../../../../../lib/api";
import type { FileInfo } from "../../../../../lib/types";
import DownloadMenu, { downloadUrl } from "../../../../../components/DownloadMenu";
import EditableTitle from "../../../../../components/workspace/EditableTitle";

function isCsv(ct: string) {
  return ct?.includes("csv") || ct === "text/csv";
}
function isHtml(ct: string) {
  return ct?.includes("html");
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
    <Suspense fallback={<div className="flex h-screen items-center justify-center text-muted">Loading…</div>}>
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

  if (loading && !readOnly)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user && !readOnly) return null;

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-5 py-2.5 text-[13px]">
        <div className="flex min-w-0 items-center gap-2">
          {readOnly && stashSlug && (
            <Link
              href={`/stashes/${stashSlug}`}
              className="text-muted hover:text-foreground"
              title={`Back to ${stashTitle ?? "Stash"}`}
            >
              ←
            </Link>
          )}
          {file ? (
            readOnly ? (
              <span className="font-mono font-medium text-foreground truncate">{file.name}</span>
            ) : (
              <EditableTitle
                value={file.name}
                className="font-mono font-medium text-foreground"
                onSave={async (next) => {
                  const updated = await updateFile(workspaceId, file.id, { name: next });
                  setFile(updated);
                  return updated.name;
                }}
              />
            )
          ) : null}
          {file && (
            <span className="text-muted">
              {file.content_type} · {formatBytes(file.size_bytes)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {readOnly && (
            <span className="rounded-md bg-surface px-2 py-1 text-[10.5px] font-medium uppercase tracking-wide text-muted">
              read-only · via Stash
            </span>
          )}
          {file?.url ? (
            <DownloadMenu
              options={[
                {
                  label: "Original file",
                  onSelect: () => void downloadUrl(file.url, file.name),
                },
              ]}
            />
          ) : (
            null
          )}
        </div>
      </div>

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
  if (isHtml(file.content_type)) {
    return (
      <iframe
        src={file.url}
        className="h-full w-full bg-white"
        sandbox="allow-scripts allow-same-origin"
        title={file.name}
      />
    );
  }
  if (isMarkdown(file.content_type, file.name)) {
    return (
      <article className="markdown-content mx-auto max-w-3xl px-12 py-8 text-[15px] leading-relaxed text-foreground">
        <Markdown remarkPlugins={[remarkGfm]}>{text || ""}</Markdown>
      </article>
    );
  }
  if (isText(file.content_type)) {
    return (
      <pre className="scroll-thin h-full overflow-auto px-5 py-4 font-mono text-[12.5px] text-foreground">
        {text || "Loading…"}
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
