"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import CustomSelect from "@/components/CustomSelect";
import {
  listUploadedItems,
  uploadFileOrPage,
  type UploadedItem,
} from "@/lib/api";
import { timeAgo } from "@/lib/utils";

type Sort = "name" | "date";

export default function UploadedFilesList() {
  const router = useRouter();
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
    router.replace(item.app_url);
  }

  const sortedItems = items && [...items].sort((a, b) => {
    if (sort === "date") return b.created_at.localeCompare(a.created_at);
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-12 py-8">
        <div className="mt-5 mb-3 flex items-center gap-2 border-b border-border pb-2.5">
          <span className="sys-label" style={{ fontSize: 10 }}>
            Sort
          </span>
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
              disabled={uploading}
              onClick={() => inputRef.current?.click()}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:cursor-default disabled:opacity-50"
            >
              {uploading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Upload className="h-3.5 w-3.5" />
              )}
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
        {error && (
          <div className="rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}
        {sortedItems?.length === 0 && (
          <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted-foreground">
            Upload files to give your agents more context.
          </div>
        )}
        {sortedItems && sortedItems.length > 0 && (
          <div className="scroll-thin overflow-x-auto rounded-lg border border-border bg-surface">
            <div className="md:min-w-[720px]">
              <div className="hidden grid-cols-[minmax(280px,1.7fr)_minmax(120px,0.7fr)_90px_88px] gap-3 border-b border-border bg-base/70 px-3 py-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground md:grid">
                <span>File</span>
                <span>Type</span>
                <span>Size</span>
                <span className="text-right">Uploaded</span>
              </div>
              {sortedItems.map((item) => (
                <button
                  type="button"
                  key={`${item.kind}:${item.id}`}
                  onClick={() => open(item)}
                  title={item.name}
                  className="grid min-h-12 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-3 py-2 text-left text-[13px] last:border-b-0 hover:bg-[var(--color-brand-50)] md:grid-cols-[minmax(280px,1.7fr)_minmax(120px,0.7fr)_90px_88px]"
                >
                  <span className="flex min-w-0 items-center gap-2 font-medium text-foreground">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="truncate">{item.name}</span>
                  </span>
                  <span className="hidden truncate text-[12px] text-muted-foreground md:block">
                    {fileType(item)}
                  </span>
                  <span className="hidden whitespace-nowrap text-[12px] text-muted-foreground md:block">
                    {formatBytes(item.size_bytes)}
                  </span>
                  <span className="justify-self-end whitespace-nowrap text-[12px] text-muted-foreground">
                    {timeAgo(item.created_at)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
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
