"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDownAZ, Clock, FileText, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import {
  listUploadedItems,
  uploadFileOrPage,
  type UploadedItem,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-store";

type Sort = "name" | "date";

export default function UploadedFilesList() {
  const router = useRouter();
  const openTab = useWorkspace((state) => state.openTab);
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

  async function upload(files: File[]) {
    if (files.length === 0) return;
    setUploading(true);
    const label = files.length === 1 ? files[0].name : `${files.length} files`;
    const toastId = toast.loading(`Uploading ${label}…`);
    try {
      for (const file of files) await uploadFileOrPage(file);
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

  function open(item: UploadedItem) {
    openTab(item.kind, item.id, { title: item.name });
    router.replace(item.app_url);
  }

  const sortedItems = items && [...items].sort((a, b) => {
    if (sort === "date") return b.created_at.localeCompare(a.created_at);
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-9 shrink-0 items-center gap-1 border-b border-[var(--divider-color)] px-2 text-[12px]">
        <span className="text-muted-foreground">Home</span>
        <span className="text-muted-foreground/50">/</span>
        <span className="font-medium text-foreground">Files</span>
        <div className="ml-auto flex items-center gap-0.5">
          <button
            type="button"
            title={sort === "name" ? "Sort by upload date" : "Sort by name"}
            aria-label={sort === "name" ? "Sort by upload date" : "Sort by name"}
            onClick={() => setSort(sort === "name" ? "date" : "name")}
            className="flex h-7 w-7 items-center justify-center rounded text-sidebar-foreground hover:bg-sidebar-accent"
          >
            {sort === "name" ? <Clock className="h-4 w-4" /> : <ArrowDownAZ className="h-4 w-4" />}
          </button>
          <button
            type="button"
            title="Upload files"
            aria-label="Upload files"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
            className="flex h-7 w-7 items-center justify-center rounded text-sidebar-foreground hover:bg-sidebar-accent disabled:opacity-50"
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
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

      <div className="min-h-0 flex-1 overflow-y-auto p-1">
        {items === null && !error && (
          <div className="flex items-center gap-2 px-3 py-2 text-[12px] text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…
          </div>
        )}
        {error && <div className="px-3 py-2 text-[12px] text-destructive">{error}</div>}
        {sortedItems?.length === 0 && (
          <div className="px-3 py-8 text-center text-[13px] text-muted-foreground">
            Upload files to give your agents more context.
          </div>
        )}
        {sortedItems?.map((item) => (
          <button
            type="button"
            key={`${item.kind}:${item.id}`}
            onClick={() => open(item)}
            title={item.name}
            className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-[13px] text-sidebar-foreground hover:bg-sidebar-accent"
          >
            <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate">{item.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
