"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
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
import { useAuth } from "../../../../../hooks/useAuth";
import {
  createFolder,
  createPage,
  getFolderContents,
  getWorkspace,
  uploadFile,
  type FolderContents,
} from "../../../../../lib/api";
import type { FileInfo, Folder, Workspace } from "../../../../../lib/types";

export default function FolderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const folderId = params.folderId as string;
  const { user, loading, logout } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [contents, setContents] = useState<FolderContents | null>(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const [workspace, folderContents] = await Promise.all([
        getWorkspace(stashId),
        getFolderContents(stashId, folderId),
      ]);
      setStash(workspace);
      setContents(folderContents);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load folder");
    }
  }, [stashId, folderId]);

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
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-12 py-8">
          {/* Breadcrumbs: stash → folder chain */}
          <nav className="mb-4 flex flex-wrap items-center gap-1.5 text-[12.5px] text-muted">
            <Link
              href={`/stashes/${stashId}`}
              className="hover:text-foreground"
            >
              {stash?.name || "Stash"}
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
                      href={`/stashes/${stashId}/folders/${crumb.id}`}
                      className="hover:text-foreground"
                    >
                      {crumb.name}
                    </Link>
                  )}
                </span>
              );
            })}
          </nav>

          <div className="mb-1 flex h-10 w-10 items-center justify-center text-4xl text-muted">
            <FolderIcon />
          </div>
          <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
            {contents?.folder.name || "Loading…"}
          </h1>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          <div className="mt-5 mb-4 flex flex-wrap items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                try {
                  const uploaded = await uploadFile(stashId, file, folderId);
                  addFileToContents(uploaded, setContents);
                } catch {
                  /* */
                }
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
            >
              + Upload file
            </button>
            <button
              onClick={async () => {
                try {
                  const p = await createPage(stashId, "Untitled", folderId);
                  router.push(`/stashes/${stashId}/p/${p.id}`);
                } catch {
                  /* */
                }
              }}
              className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
            >
              + New page
            </button>
            <button
              onClick={async () => {
                const name = window.prompt("Folder name?");
                if (!name?.trim()) return;
                try {
                  const folder = await createFolder(stashId, name.trim(), folderId);
                  addSubfolderToContents(folder, setContents);
                } catch {
                  /* */
                }
              }}
              className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
            >
              + New folder
            </button>
          </div>

          {/* Contents grid — same card style as the stash home Wiki section */}
          {contents && (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {contents.subfolders.map((sub) => (
                <Link
                  key={sub.id}
                  href={`/stashes/${stashId}/folders/${sub.id}`}
                  className="flex items-center gap-3 rounded-lg border border-border bg-base p-3 text-left transition-colors hover:border-[var(--color-brand-200)] hover:bg-[var(--color-brand-50)]"
                >
                  <span className="flex h-7 w-7 items-center justify-center text-2xl text-muted">
                    <FolderIcon />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-[13.5px] font-semibold text-foreground">
                      {sub.name}
                    </div>
                    <div className="truncate text-[11.5px] text-muted">
                      {[
                        sub.page_count
                          ? `${sub.page_count} page${sub.page_count === 1 ? "" : "s"}`
                          : null,
                        sub.file_count
                          ? `${sub.file_count} file${sub.file_count === 1 ? "" : "s"}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "Empty"}
                    </div>
                  </div>
                </Link>
              ))}
              {contents.pages.map((p) => (
                <Link
                  key={p.id}
                  href={`/stashes/${stashId}/p/${p.id}`}
                  className="flex items-center gap-3 rounded-lg border border-border bg-base p-3 text-left transition-colors hover:border-[var(--color-brand-200)] hover:bg-[var(--color-brand-50)]"
                >
                  <span className="flex h-7 w-7 items-center justify-center text-2xl text-muted">
                    <PageIcon />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-[13.5px] font-semibold text-foreground">
                      {p.name.replace(/\.md$/, "")}
                    </div>
                    <div className="truncate text-[11.5px] text-muted">Page</div>
                  </div>
                </Link>
              ))}
              {contents.files.map((f) => {
                const isCsvLinked =
                  f.content_type?.includes("csv") && f.linked_table_id;
                const href = isCsvLinked
                  ? `/tables/${f.linked_table_id}?workspaceId=${stashId}`
                  : `/stashes/${stashId}/f/${f.id}`;
                return (
                  <Link
                    key={f.id}
                    href={href}
                    className="flex items-center gap-3 rounded-lg border border-border bg-base p-3 text-left transition-colors hover:border-[var(--color-brand-200)] hover:bg-[var(--color-brand-50)]"
                  >
                    <span
                      className={
                        "flex h-7 w-7 items-center justify-center text-2xl " +
                        (f.content_type?.includes("csv")
                          ? "text-emerald-600"
                          : f.content_type?.includes("pdf")
                          ? "text-rose-500"
                          : f.content_type?.includes("html")
                          ? "text-amber-600"
                          : "text-muted")
                      }
                    >
                      {f.content_type?.includes("csv") ? <TableIcon /> : <FileIcon />}
                    </span>
                    <div className="min-w-0">
                      <div className="truncate text-[13.5px] font-semibold text-foreground">
                        {f.name}
                      </div>
                      <div className="truncate text-[11.5px] text-muted">
                        {f.content_type || "file"} · {formatBytes(f.size_bytes)}
                      </div>
                    </div>
                  </Link>
                );
              })}
              {contents.subfolders.length === 0 &&
                contents.pages.length === 0 &&
                contents.files.length === 0 && (
                  <div className="col-span-full rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
                    Empty folder. Add a page, upload a file, or create a subfolder.
                  </div>
                )}
            </div>
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
