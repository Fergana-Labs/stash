"use client";

import { type DragEvent, useRef, useState } from "react";

import { createFolder, uploadFileOrPage } from "@/lib/api";

type VaultStatus =
  | { kind: "idle" }
  | { kind: "busy"; message: string }
  | { kind: "done"; message: string }
  | { kind: "error"; message: string };

type Props = {
  onUploaded: (uploadedCount: number) => void;
};

// Folder-only drop zone for the Obsidian vault import. Drag-or-click,
// recursive walk via webkitGetAsEntry (drop) or webkitRelativePath
// (browse), parents-first folder creation, files routed to
// uploadFileOrPage which makes .md/.html into pages and lands others
// in Files.
export default function ObsidianVaultDropZone({ onUploaded }: Props) {
  const [dragActive, setDragActive] = useState(false);
  const [status, setStatus] = useState<VaultStatus>({ kind: "idle" });
  const folderInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  async function readAllEntries(reader: FileSystemDirectoryReader) {
    const all: FileSystemEntry[] = [];
    for (;;) {
      const batch: FileSystemEntry[] = await new Promise((resolve, reject) =>
        reader.readEntries(resolve, reject),
      );
      if (!batch.length) break;
      all.push(...batch);
    }
    return all;
  }

  async function flattenEntries(
    entries: FileSystemEntry[],
    prefix: string[] = [],
  ): Promise<{ file: File; path: string[] }[]> {
    const out: { file: File; path: string[] }[] = [];
    for (const entry of entries) {
      if (entry.isFile) {
        const file = await new Promise<File>((resolve, reject) =>
          (entry as FileSystemFileEntry).file(resolve, reject),
        );
        out.push({ file, path: prefix });
      } else if (entry.isDirectory) {
        // Skip Obsidian's internal config / plugin cruft.
        if (entry.name === ".obsidian" || entry.name.startsWith(".")) continue;
        const reader = (entry as FileSystemDirectoryEntry).createReader();
        const children = await readAllEntries(reader);
        const nested = await flattenEntries(children, [...prefix, entry.name]);
        out.push(...nested);
      }
    }
    return out;
  }

  async function uploadWithPaths(items: { file: File; path: string[] }[]) {
    if (!items.length) return;
    setStatus({ kind: "busy", message: `Uploading ${items.length} files…` });

    const folderCache = new Map<string, string>();
    folderCache.set("", "");

    async function ensureFolder(path: string[]): Promise<string | null> {
      if (path.length === 0) return null;
      const key = path.join("/");
      const cached = folderCache.get(key);
      if (cached !== undefined) return cached || null;
      const parentId = await ensureFolder(path.slice(0, -1));
      const folder = await createFolder(path[path.length - 1], parentId);
      folderCache.set(key, folder.id);
      return folder.id;
    }

    let uploaded = 0;
    try {
      for (const { file, path } of items) {
        const folderId = await ensureFolder(path);
        await uploadFileOrPage(file, folderId);
        uploaded += 1;
      }
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof Error ? e.message : "Upload failed",
      });
      return;
    }
    setStatus({
      kind: "done",
      message: `Uploaded ${uploaded} file${uploaded === 1 ? "" : "s"} from your vault.`,
    });
    if (uploaded > 0) onUploaded(uploaded);
  }

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setDragActive(false);
    const items = e.dataTransfer.items ? Array.from(e.dataTransfer.items) : [];
    const entries = items
      .filter((it) => it.kind === "file")
      .map((it) => it.webkitGetAsEntry?.())
      .filter((x): x is FileSystemEntry => !!x);
    if (entries.length === 0) {
      setStatus({
        kind: "error",
        message: "Drop a folder (not a single file).",
      });
      return;
    }
    const flat = await flattenEntries(entries);
    await uploadWithPaths(flat);
  }

  async function handleBrowsed(files: FileList) {
    const items: { file: File; path: string[] }[] = [];
    for (const file of Array.from(files)) {
      const rel = (file as File & { webkitRelativePath?: string })
        .webkitRelativePath;
      const parts = rel ? rel.split("/").slice(0, -1) : [];
      // Skip Obsidian internals.
      if (parts.some((p) => p === ".obsidian" || p.startsWith("."))) continue;
      items.push({ file, path: parts });
    }
    await uploadWithPaths(items);
  }

  function isFilesDrag(e: DragEvent) {
    return Array.from(e.dataTransfer.types).includes("Files");
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => folderInputRef.current?.click()}
        onDragEnter={(e) => {
          if (!isFilesDrag(e)) return;
          e.preventDefault();
          e.stopPropagation();
          dragDepth.current += 1;
          setDragActive(true);
        }}
        onDragLeave={(e) => {
          if (!isFilesDrag(e)) return;
          e.preventDefault();
          e.stopPropagation();
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragActive(false);
        }}
        onDragOver={(e) => {
          if (!isFilesDrag(e)) return;
          e.preventDefault();
          e.stopPropagation();
          e.dataTransfer.dropEffect = "copy";
        }}
        onDrop={handleDrop}
        className={`w-full cursor-pointer flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragActive
            ? "border-brand bg-brand/10"
            : "border-border bg-background/40 hover:border-brand hover:bg-raised"
        }`}
      >
        <div className="text-[24px] leading-none" aria-hidden>
          📁
        </div>
        <div className="text-[13px] font-medium text-foreground">
          {dragActive
            ? "Release to upload your vault"
            : "Drop a vault folder, or click to browse"}
        </div>
        <div className="text-[11px] text-muted">
          <code className="text-foreground">.obsidian/</code> and other dot-
          folders are skipped automatically.
        </div>
      </button>

      <input
        ref={folderInputRef}
        type="file"
        multiple
        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) void handleBrowsed(e.target.files);
          if (folderInputRef.current) folderInputRef.current.value = "";
        }}
      />

      {status.kind !== "idle" && (
        <p
          className={`text-[11.5px] ${
            status.kind === "error"
              ? "text-error"
              : status.kind === "done"
                ? "text-brand"
                : "text-muted"
          }`}
        >
          {status.message}
        </p>
      )}
    </div>
  );
}
