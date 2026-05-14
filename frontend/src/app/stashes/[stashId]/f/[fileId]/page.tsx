"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  getFile,
  getFolderContents,
  ingestCsvFile,
  type FolderBreadcrumb,
} from "../../../../../lib/api";
import type { FileInfo } from "../../../../../lib/types";

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
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const fileId = params.fileId as string;
  const { user, loading, logout } = useAuth();

  const [file, setFile] = useState<FileInfo | null>(null);
  const [folderChain, setFolderChain] = useState<FolderBreadcrumb[]>([]);
  const [textBody, setTextBody] = useState<string | null>(null);
  const [error, setError] = useState("");

  useBreadcrumbs(
    [
      ...folderChain.map((c) => ({
        label: c.name,
        href: `/stashes/${stashId}/folders/${c.id}`,
      })),
      { label: file ? file.name : "File" },
    ],
    `${stashId}/file/${fileId}/${file?.name ?? ""}/${folderChain.map((c) => c.id).join(",")}`
  );

  const load = useCallback(async () => {
    try {
      const f = await getFile(stashId, fileId);
      setFile(f);
      if (f.folder_id) {
        try {
          const contents = await getFolderContents(stashId, f.folder_id);
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
          router.replace(`/tables/${f.linked_table_id}?workspaceId=${stashId}`);
        } else {
          try {
            const table = await ingestCsvFile(stashId, fileId);
            router.replace(`/tables/${table.id}?workspaceId=${stashId}`);
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
  }, [stashId, fileId, router]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-5 py-2.5 text-[13px]">
          <div className="flex items-center gap-2">
            <span className="font-mono font-medium text-foreground">{file?.name}</span>
            {file && (
              <span className="text-muted">
                {file.content_type} · {formatBytes(file.size_bytes)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {/* "Share" checkbox is gone — sharing is now link-based. Mint a
                share-link with target_type='file' via the workspace Share
                button. */}
            {file?.url && (
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                download={file.name}
                className="rounded-md p-1.5 text-muted hover:bg-raised"
                title="Download"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
                </svg>
              </a>
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
