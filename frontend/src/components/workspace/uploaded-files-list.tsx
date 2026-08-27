"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, FileText, Folder, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import CustomSelect from "@/components/CustomSelect";
import {
  listUploadedItems,
  uploadFileOrPage,
  type UploadedItem,
} from "@/lib/api";
import { timeAgo } from "@/lib/utils";

type Sort = "name" | "date";
type UploadFolder = UploadedItem["folder_path"][number];

export default function UploadedFilesList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentFolderId = searchParams.get("folder");
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadedItem[] | null>(null);
  const [sort, setSort] = useState<Sort>("date");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await listUploadedItems());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load files");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const currentPath = useMemo(
    () => findFolderPath(items, currentFolderId),
    [items, currentFolderId],
  );
  const folderMissing = items !== null && currentFolderId !== null && currentPath === null;
  const visibleFolders = useMemo(
    () => childFolders(items, currentFolderId),
    [items, currentFolderId],
  );
  const visibleItems = useMemo(() => {
    if (!items || folderMissing) return [];
    const directItems = items.filter(
      (item) => (item.folder_path.at(-1)?.id ?? null) === currentFolderId,
    );
    return directItems.sort((a, b) => {
      if (sort === "date") return b.created_at.localeCompare(a.created_at);
      return a.name.localeCompare(b.name);
    });
  }, [items, currentFolderId, folderMissing, sort]);

  const breadcrumbs = [
    { label: "Files", href: "/files", area: "files" as const },
    ...(currentPath ?? []).map((folder) => ({
      label: folder.name,
      href: `/files?folder=${folder.id}`,
    })),
  ];
  useBreadcrumbs(
    breadcrumbs,
    `files/${currentFolderId ?? "root"}/${breadcrumbs.map((crumb) => crumb.label).join("/")}`,
  );

  async function upload(files: File[]) {
    if (files.length === 0) return;
    setUploading(true);
    const label = files.length === 1 ? files[0].name : `${files.length} files`;
    const toastId = toast.loading(`Uploading ${label}…`);
    try {
      for (const file of files) await uploadFileOrPage(file, currentFolderId);
      await load();
      toast.success(`Uploaded ${label}`, { id: toastId });
    } catch (uploadError) {
      toast.error(uploadError instanceof Error ? uploadError.message : "Upload failed", {
        id: toastId,
      });
    } finally {
      setUploading(false);
    }
  }

  const hasRows = visibleFolders.length > 0 || visibleItems.length > 0;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-12 py-8">
        <nav className="flex min-h-8 items-center gap-1 text-[13px]" aria-label="File location">
          {breadcrumbs.map((crumb, index) => (
            <span key={crumb.href} className="flex min-w-0 items-center gap-1">
              {index > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
              <button
                type="button"
                onClick={() => router.push(crumb.href)}
                className="max-w-48 truncate font-medium text-muted-foreground hover:text-foreground"
              >
                {crumb.label}
              </button>
            </span>
          ))}
        </nav>

        <div className="mt-3 mb-3 flex items-center gap-2 border-b border-border pb-2.5">
          <span className="sys-label" style={{ fontSize: 10 }}>Sort</span>
          <CustomSelect
            ariaLabel="Sort"
            value={sort}
            options={[
              { value: "date", label: "Recent" },
              { value: "name", label: "Name" },
            ]}
            onChange={(value) => setSort(value as Sort)}
          />
          <div className="ml-auto">
            <button
              type="button"
              aria-label="Upload files"
              disabled={uploading || folderMissing}
              onClick={() => inputRef.current?.click()}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:cursor-default disabled:opacity-50"
            >
              {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
              Upload
            </button>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = "";
                void upload(files);
              }}
            />
          </div>
        </div>

        {items === null && !error && (
          <div className="flex items-center gap-2 px-3 py-8 text-[12px] text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…
          </div>
        )}
        {(error || folderMissing) && (
          <div className="rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error ?? "This upload folder does not exist."}
          </div>
        )}
        {items !== null && !folderMissing && !hasRows && (
          <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted-foreground">
            Upload files to give your agents more context.
          </div>
        )}
        {items !== null && !folderMissing && hasRows && (
          <div className="scroll-thin overflow-x-auto rounded-lg border border-border bg-surface">
            <div className="md:min-w-[720px]">
              <div className="hidden grid-cols-[minmax(280px,1.7fr)_minmax(120px,0.7fr)_90px_88px] gap-3 border-b border-border bg-base/70 px-3 py-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground md:grid">
                <span>Name</span><span>Type</span><span>Size</span><span className="text-right">Uploaded</span>
              </div>
              {visibleFolders.map((folder) => (
                <button
                  type="button"
                  key={`folder:${folder.id}`}
                  onClick={() => router.push(`/files?folder=${folder.id}`)}
                  className={rowClassName}
                >
                  <span className="flex min-w-0 items-center gap-2 font-medium text-foreground">
                    <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="truncate">{folder.name}</span>
                  </span>
                  <span className="hidden text-[12px] text-muted-foreground md:block">Folder</span>
                  <span className="hidden text-[12px] text-muted-foreground md:block">—</span>
                  <span className="justify-self-end text-[12px] text-muted-foreground">—</span>
                </button>
              ))}
              {visibleItems.map((item) => (
                <button
                  type="button"
                  key={`${item.kind}:${item.id}`}
                  onClick={() => router.push(item.app_url)}
                  title={item.name}
                  className={rowClassName}
                >
                  <span className="flex min-w-0 items-center gap-2 font-medium text-foreground">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="truncate">{item.name}</span>
                  </span>
                  <span className="hidden truncate text-[12px] text-muted-foreground md:block">{fileType(item)}</span>
                  <span className="hidden whitespace-nowrap text-[12px] text-muted-foreground md:block">{formatBytes(item.size_bytes)}</span>
                  <span className="justify-self-end whitespace-nowrap text-[12px] text-muted-foreground">{timeAgo(item.created_at)}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const rowClassName = "grid min-h-12 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-3 py-2 text-left text-[13px] last:border-b-0 hover:bg-[var(--color-brand-50)] md:grid-cols-[minmax(280px,1.7fr)_minmax(120px,0.7fr)_90px_88px]";

function findFolderPath(items: UploadedItem[] | null, folderId: string | null): UploadFolder[] | null {
  if (folderId === null) return [];
  if (!items) return null;
  for (const item of items) {
    const index = item.folder_path.findIndex((folder) => folder.id === folderId);
    if (index >= 0) return item.folder_path.slice(0, index + 1);
  }
  return null;
}

function childFolders(items: UploadedItem[] | null, folderId: string | null): UploadFolder[] {
  if (!items) return [];
  const folders = new Map<string, UploadFolder>();
  for (const item of items) {
    const parentIndex = folderId === null
      ? -1
      : item.folder_path.findIndex((folder) => folder.id === folderId);
    if (folderId !== null && parentIndex < 0) continue;
    const child = item.folder_path[parentIndex + 1];
    if (child) folders.set(child.id, child);
  }
  return [...folders.values()].sort((a, b) => a.name.localeCompare(b.name));
}

function fileType(item: UploadedItem): string {
  if (item.kind === "page") return item.content_type === "html" ? "HTML" : "Markdown";
  const subtype = item.content_type.split("/")[1];
  return subtype ? subtype.toUpperCase() : "File";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
