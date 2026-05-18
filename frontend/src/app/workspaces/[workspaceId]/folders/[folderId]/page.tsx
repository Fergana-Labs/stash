"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  FileIcon,
  FolderIcon,
  PageIcon,
  TableIcon,
} from "../../../../../components/StashIcons";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  createFolder,
  createPage,
  getFolderContents,
  uploadFile,
  type FolderContents,
  type FolderSubfolder,
} from "../../../../../lib/api";
import type { FileInfo, Folder } from "../../../../../lib/types";

type LiveFile = FolderContents["files"][number];
type LivePage = FolderContents["pages"][number];

export default function FolderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const folderId = params.folderId as string;
  const { user, loading } = useAuth();

  const [contents, setContents] = useState<FolderContents | null>(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const folderPath = contents?.breadcrumbs ?? [];
  const breadcrumbs =
    folderPath.length > 0
      ? [
          ...folderPath.slice(0, -1).map((crumb) => ({
            label: crumb.name,
            href: `/workspaces/${workspaceId}/folders/${crumb.id}`,
          })),
          { label: contents?.folder.name ?? "Folder" },
        ]
      : [{ label: "Folder" }];

  useBreadcrumbs(
    breadcrumbs,
    `${workspaceId}/folder/${folderId}/${folderPath.map((c) => c.id).join(",")}`
  );

  const load = useCallback(async () => {
    try {
      const folderContents = await getFolderContents(workspaceId, folderId);
      setContents(folderContents);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load folder");
    }
  }, [workspaceId, folderId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const grouped = useMemo(() => {
    if (!contents) return null;
    const tables = contents.files.filter((f) => f.content_type?.includes("csv"));
    const files = contents.files.filter((f) => !f.content_type?.includes("csv"));
    return {
      folders: contents.subfolders,
      pages: contents.pages,
      tables,
      files,
    };
  }, [contents]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[980px] px-12 pb-20 pt-8">
        {/* Breadcrumb path */}
        <div className="flex items-center gap-1.5 text-[12.5px] text-muted">
          <Link href={`/workspaces/${workspaceId}`} className="text-dim hover:text-foreground">
            Home
          </Link>
          {contents?.breadcrumbs.map((crumb, i) => {
            const isLast = i === contents.breadcrumbs.length - 1;
            return (
              <span key={crumb.id} className="flex items-center gap-1.5">
                <span className="text-muted/60">/</span>
                {isLast ? (
                  <span className="font-medium text-foreground">{crumb.name}</span>
                ) : (
                  <Link
                    href={`/workspaces/${workspaceId}/folders/${crumb.id}`}
                    className="hover:text-foreground"
                  >
                    {crumb.name}
                  </Link>
                )}
              </span>
            );
          })}
        </div>

        {/* Header */}
        <div className="mt-3.5 flex items-end justify-between gap-4">
          <div className="min-w-0">
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-[10px] border border-border bg-surface text-dim">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
              </svg>
            </span>
            <h1 className="mb-1 mt-2.5 font-display text-[30px] font-bold tracking-[-0.02em]">
              {contents?.folder.name || "Loading…"}
            </h1>
            {grouped && (
              <div className="flex items-center gap-2 text-[12.5px] text-muted">
                <span>
                  {grouped.folders.length} folder{grouped.folders.length === 1 ? "" : "s"} ·{" "}
                  {grouped.pages.length} page{grouped.pages.length === 1 ? "" : "s"} ·{" "}
                  {grouped.tables.length} table{grouped.tables.length === 1 ? "" : "s"} ·{" "}
                  {grouped.files.length} file{grouped.files.length === 1 ? "" : "s"}
                </span>
              </div>
            )}
          </div>
          <div className="flex flex-shrink-0 gap-1.5">
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                try {
                  const uploaded = await uploadFile(workspaceId, file, folderId);
                  addFileToContents(uploaded, setContents);
                } catch {
                  /* */
                }
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
            />
            <ToolbarButton
              onClick={() => fileInputRef.current?.click()}
              label="Upload file"
            />
            <ToolbarButton
              onClick={async () => {
                try {
                  const p = await createPage(workspaceId, "Untitled", folderId);
                  router.push(`/workspaces/${workspaceId}/p/${p.id}`);
                } catch {
                  /* */
                }
              }}
              label="New page"
            />
            <ToolbarButton
              onClick={async () => {
                const name = window.prompt("Folder name?");
                if (!name?.trim()) return;
                try {
                  const folder = await createFolder(workspaceId, name.trim(), folderId);
                  addSubfolderToContents(folder, setContents);
                } catch {
                  /* */
                }
              }}
              label="New folder"
            />
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {grouped && (
          <>
            {grouped.folders.length === 0 &&
              grouped.pages.length === 0 &&
              grouped.tables.length === 0 &&
              grouped.files.length === 0 && (
                <div className="mt-10 rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted">
                  Empty folder. Add a page, upload a file, or create a subfolder.
                </div>
              )}

            {grouped.folders.length > 0 && (
              <Section title="Folders" count={grouped.folders.length}>
                {grouped.folders.map((sub) => (
                  <FolderTile key={sub.id} sub={sub} workspaceId={workspaceId} />
                ))}
              </Section>
            )}
            {grouped.pages.length > 0 && (
              <Section title="Pages" count={grouped.pages.length}>
                {grouped.pages.map((p) => (
                  <PageTile key={p.id} page={p} workspaceId={workspaceId} />
                ))}
              </Section>
            )}
            {grouped.tables.length > 0 && (
              <Section title="Tables" count={grouped.tables.length}>
                {grouped.tables.map((f) => (
                  <TableTile key={f.id} file={f} workspaceId={workspaceId} />
                ))}
              </Section>
            )}
            {grouped.files.length > 0 && (
              <Section title="Files" count={grouped.files.length}>
                {grouped.files.map((f) => (
                  <FileTile key={f.id} file={f} workspaceId={workspaceId} />
                ))}
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-[22px]">
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="m-0 font-display text-[14px] font-semibold">{title}</h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {count}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">{children}</div>
    </section>
  );
}

function ToolbarButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-base px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised"
    >
      <PlusGlyph /> {label}
    </button>
  );
}

function FolderTile({ sub, workspaceId }: { sub: FolderSubfolder; workspaceId: string }) {
  const sub_label =
    [
      sub.page_count ? `${sub.page_count} page${sub.page_count === 1 ? "" : "s"}` : null,
      sub.file_count ? `${sub.file_count} file${sub.file_count === 1 ? "" : "s"}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || "Empty";
  return (
    <Link href={`/workspaces/${workspaceId}/folders/${sub.id}`} className="linkrow items-start px-3.5 py-3">
      <span className="mt-0.5 text-muted">
        <FolderIcon />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-semibold text-foreground">{sub.name}</div>
        <div className="mt-0.5 text-[11.5px] text-muted">{sub_label}</div>
      </div>
    </Link>
  );
}

function PageTile({ page, workspaceId }: { page: LivePage; workspaceId: string }) {
  const isHtml = page.name.endsWith(".html");
  return (
    <Link href={`/workspaces/${workspaceId}/p/${page.id}`} className="linkrow items-start px-3.5 py-3">
      <span className={"mt-0.5 " + (isHtml ? "text-[#D97706]" : "text-muted")}>
        <PageIcon />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-semibold text-foreground">
          {page.name.replace(/\.md$/, "")}
        </div>
        <div className="mt-0.5 text-[11.5px] text-muted">
          Page · {isHtml ? "html" : "markdown"}
        </div>
      </div>
    </Link>
  );
}

function TableTile({ file, workspaceId }: { file: LiveFile; workspaceId: string }) {
  const href = file.linked_table_id
    ? `/tables/${file.linked_table_id}?workspaceId=${workspaceId}`
    : `/workspaces/${workspaceId}/f/${file.id}`;
  return (
    <Link href={href} className="linkrow items-start px-3.5 py-3">
      <span className="mt-0.5 text-emerald-600">
        <TableIcon />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-semibold text-foreground">{file.name}</div>
        <div className="mt-0.5 text-[11.5px] text-muted">Table · {formatBytes(file.size_bytes)}</div>
      </div>
    </Link>
  );
}

function FileTile({ file, workspaceId }: { file: LiveFile; workspaceId: string }) {
  const tint = file.content_type?.includes("pdf")
    ? "text-rose-500"
    : file.content_type?.includes("image")
      ? "text-violet-600"
      : file.content_type?.includes("html")
        ? "text-amber-600"
        : "text-muted";
  return (
    <Link
      href={`/workspaces/${workspaceId}/f/${file.id}`}
      className="linkrow items-start px-3.5 py-3"
    >
      <span className={"mt-0.5 " + tint}>
        <FileIcon />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-semibold text-foreground">{file.name}</div>
        <div className="mt-0.5 text-[11.5px] text-muted">
          {file.content_type || "file"} · {formatBytes(file.size_bytes)}
        </div>
      </div>
    </Link>
  );
}

function PlusGlyph() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function addSubfolderToContents(
  folder: Folder,
  setContents: Dispatch<SetStateAction<FolderContents | null>>
) {
  setContents((current) => {
    if (!current) return current;
    const subfolders = [
      ...current.subfolders,
      { id: folder.id, name: folder.name, page_count: 0, file_count: 0 },
    ].sort((a, b) => a.name.localeCompare(b.name));
    return { ...current, subfolders };
  });
}

function addFileToContents(
  file: FileInfo,
  setContents: Dispatch<SetStateAction<FolderContents | null>>
) {
  setContents((current) => {
    if (!current) return current;
    const nextFile = {
      id: file.id,
      name: file.name,
      size_bytes: file.size_bytes,
      content_type: file.content_type,
      url: file.url,
      created_at: file.created_at,
      linked_table_id: file.linked_table_id ?? null,
    };
    return { ...current, files: [nextFile, ...current.files] };
  });
}
