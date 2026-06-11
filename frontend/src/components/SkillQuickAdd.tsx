"use client";

import { useRef, useState, type DragEvent, type FormEvent } from "react";
import {
  createFolder,
  createPage,
  updateSkill,
  uploadFileOrPage,
  uploadTranscript,
  type SkillItemSpec,
} from "../lib/api";

interface SkillQuickAddProps {
  workspaceId: string;
  onAdded?: () => void;
  // When set, newly-created pages and files are also appended to this
  // skill's items so the quick-add doubles as "add to this skill".
  skillId?: string;
  existingItems?: SkillItemSpec[];
}

type Status = "idle" | "saving" | "saved" | "error";

const URL_RE = /^https?:\/\/\S+$/i;

// createReader().readEntries only returns a batch at a time — keep reading
// until it returns empty so we capture every entry in a wide directory.
async function readAllEntries(
  reader: FileSystemDirectoryReader,
): Promise<FileSystemEntry[]> {
  const all: FileSystemEntry[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) =>
      reader.readEntries(resolve, reject),
    );
    if (!batch.length) break;
    all.push(...batch);
  }
  return all;
}

export default function SkillQuickAdd({
  workspaceId,
  onAdded,
  skillId,
  existingItems,
}: SkillQuickAddProps) {
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [dragActive, setDragActive] = useState(false);
  const [hint, setHint] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  // Track nested dragenter/leave so we don't flicker when crossing children
  const dragDepth = useRef(0);

  function flashHint(text: string, ms = 1500) {
    setHint(text);
    window.setTimeout(() => setHint(""), ms);
  }

  // Append newly-created items to the host skill. Backend wants the full
  // ordered item list on PATCH, so we union existing + new.
  async function appendToSkill(newItems: SkillItemSpec[]) {
    if (!skillId || newItems.length === 0) return;
    const base = (existingItems ?? []).map((it, i) => ({ ...it, position: i }));
    const merged = [
      ...base,
      ...newItems.map((it, i) => ({ ...it, position: base.length + i })),
    ];
    await updateSkill(skillId, { items: merged });
  }

  const targetLabel = skillId ? "Skill" : "Files";

  async function handleTextSubmit(e: FormEvent) {
    e.preventDefault();
    const text = value.trim();
    if (!text || status === "saving") return;

    setStatus("saving");
    try {
      const isUrl = URL_RE.test(text);
      const title = isUrl
        ? text.replace(/^https?:\/\//, "").slice(0, 80)
        : text.split("\n")[0].slice(0, 80) || "Note";
      const body = isUrl ? `<${text}>` : text;
      const page = await createPage(workspaceId, title, undefined, body);
      await appendToSkill([{ object_type: "page", object_id: page.id }]);
    } catch {
      setStatus("error");
      flashHint("Couldn't save — try again", 2500);
      window.setTimeout(() => setStatus("idle"), 2500);
      return;
    }
    setValue("");
    setStatus("saved");
    flashHint(`Added to ${targetLabel}`);
    onAdded?.();
    window.setTimeout(() => setStatus("idle"), 1500);
  }

  async function handleFiles(files: FileList | File[]) {
    const list = Array.from(files);
    if (!list.length || status === "saving") return;
    setStatus("saving");
    flashHint(list.length === 1 ? `Uploading ${list[0].name}…` : `Uploading ${list.length} files…`, 8000);
    let sessionCount = 0;
    let fileCount = 0;
    const newItems: SkillItemSpec[] = [];
    try {
      for (const f of list) {
        // .jsonl transcripts are sessions, not files — same drop target,
        // different code path. Anything else goes to Files.
        if (f.name.toLowerCase().endsWith(".jsonl")) {
          const sessionId = f.name.replace(/\.jsonl$/i, "").trim() || "session";
          await uploadTranscript(workspaceId, f, sessionId, "manual-upload");
          sessionCount += 1;
          // .jsonl flows land in the workspace's sessions list; quick-add
          // doesn't auto-attach them to the host skill (use Add things).
        } else {
          const result = await uploadFileOrPage(workspaceId, f);
          fileCount += 1;
          if (result.kind === "page") {
            newItems.push({ object_type: "page", object_id: result.page.id });
          } else {
            newItems.push({ object_type: "file", object_id: result.file.id });
          }
        }
      }
      await appendToSkill(newItems);
    } catch {
      setStatus("error");
      flashHint("Upload failed — try again", 2500);
      window.setTimeout(() => setStatus("idle"), 2500);
      return;
    }
    setStatus("saved");
    const parts: string[] = [];
    if (sessionCount > 0) parts.push(`${sessionCount} session${sessionCount === 1 ? "" : "s"}`);
    if (fileCount > 0) parts.push(`${fileCount} file${fileCount === 1 ? "" : "s"}`);
    flashHint(parts.length ? `Added ${parts.join(" + ")}` : "Added");
    onAdded?.();
    window.setTimeout(() => setStatus("idle"), 1500);
  }

  function isFilesDrag(e: DragEvent) {
    return Array.from(e.dataTransfer.types).includes("Files");
  }

  function handleDragEnter(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current += 1;
    setDragActive(true);
  }

  function handleDragLeave(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragActive(false);
  }

  function handleDragOver(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";
  }

  function handleDrop(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setDragActive(false);

    // If any dropped item is a directory entry, walk the tree so we preserve
    // folder structure. Otherwise fall back to the flat-file path.
    const items = e.dataTransfer.items ? Array.from(e.dataTransfer.items) : [];
    const entries = items
      .filter((it) => it.kind === "file")
      .map((it) => it.webkitGetAsEntry?.())
      .filter((e): e is FileSystemEntry => !!e);
    const hasDirectory = entries.some((entry) => entry.isDirectory);

    if (hasDirectory) {
      void handleEntries(entries);
      return;
    }
    if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
  }

  // Walk an array of FileSystemEntry (mix of files + dirs) into a flat list
  // of {file, path[]} where path is the folder chain from drop root.
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
        const reader = (entry as FileSystemDirectoryEntry).createReader();
        const children: FileSystemEntry[] = await readAllEntries(reader);
        const nested = await flattenEntries(children, [...prefix, entry.name]);
        out.push(...nested);
      }
    }
    return out;
  }

  async function handleEntries(entries: FileSystemEntry[]) {
    const items = await flattenEntries(entries);
    await uploadWithPaths(items);
  }

  async function handleDirectoryInput(files: FileList) {
    // webkitdirectory input gives us a FileList where each file's
    // .webkitRelativePath is "rootDir/subDir/.../name". Split into path
    // segments (drop the filename, last segment) and feed the same uploader.
    const items: { file: File; path: string[] }[] = [];
    for (const file of Array.from(files)) {
      const rel = (file as File & { webkitRelativePath?: string })
        .webkitRelativePath;
      const parts = rel ? rel.split("/").slice(0, -1) : [];
      items.push({ file, path: parts });
    }
    await uploadWithPaths(items);
  }

  // Create the folder hierarchy on demand, then upload each file into its
  // resolved parent. Folders are created depth-first so each level finds
  // its parent in the cache. Cache key is the joined path.
  async function uploadWithPaths(items: { file: File; path: string[] }[]) {
    if (!items.length || status === "saving") return;
    setStatus("saving");
    flashHint(`Uploading ${items.length} file${items.length === 1 ? "" : "s"}…`, 8000);

    const folderCache = new Map<string, string>();
    folderCache.set("", ""); // root sentinel

    async function ensureFolder(path: string[]): Promise<string | null> {
      if (path.length === 0) return null;
      const key = path.join("/");
      const cached = folderCache.get(key);
      if (cached !== undefined) return cached || null;

      // Recursively ensure every ancestor exists. Files visited in arbitrary
      // order can hit deeply-nested paths first; without recursion we'd
      // create the leaf folder at root and orphan it from its parent.
      const parentId = await ensureFolder(path.slice(0, -1));
      const folder = await createFolder(workspaceId, path[path.length - 1], parentId);
      folderCache.set(key, folder.id);
      return folder.id;
    }

    const newItems: SkillItemSpec[] = [];
    let fileCount = 0;
    let sessionCount = 0;
    try {
      for (const { file, path } of items) {
        const folderId = await ensureFolder(path);
        if (file.name.toLowerCase().endsWith(".jsonl")) {
          const sessionId = file.name.replace(/\.jsonl$/i, "").trim() || "session";
          await uploadTranscript(workspaceId, file, sessionId, "manual-upload");
          sessionCount += 1;
        } else {
          const result = await uploadFileOrPage(workspaceId, file, folderId);
          fileCount += 1;
          if (result.kind === "page") {
            newItems.push({ object_type: "page", object_id: result.page.id });
          } else {
            newItems.push({ object_type: "file", object_id: result.file.id });
          }
        }
      }
      await appendToSkill(newItems);
    } catch {
      setStatus("error");
      flashHint("Upload failed — try again", 2500);
      window.setTimeout(() => setStatus("idle"), 2500);
      return;
    }
    setStatus("saved");
    const parts: string[] = [];
    if (sessionCount > 0) parts.push(`${sessionCount} session${sessionCount === 1 ? "" : "s"}`);
    if (fileCount > 0) parts.push(`${fileCount} file${fileCount === 1 ? "" : "s"}`);
    flashHint(parts.length ? `Added ${parts.join(" + ")}` : "Added");
    onAdded?.();
    window.setTimeout(() => setStatus("idle"), 1500);
  }

  const statusText =
    hint ||
    (status === "saved" ? `Added to ${targetLabel}` : "");
  const statusTone =
    status === "error"
      ? "text-red-500"
      : status === "saved"
      ? "text-[var(--color-brand-700)]"
      : "text-muted";

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      className={
        "group relative transition-colors " +
        (dragActive
          ? "rounded-xl border-2 border-dashed border-[var(--color-brand-500)] bg-[var(--color-brand-50)] p-1"
          : "")
      }
    >
      <form
        onSubmit={handleTextSubmit}
        className="flex items-center gap-2 rounded-lg border border-border bg-base px-3 py-2 focus-within:border-[var(--color-brand-500)] focus-within:ring-1 focus-within:ring-[var(--color-brand-200)]"
      >
        <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-[var(--color-brand-500)] text-[14px] font-semibold leading-none text-white">
          +
        </span>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={
            dragActive
              ? `Drop to add to ${targetLabel}…`
              : "Paste a link, type a note, or drop a file"
          }
          disabled={status === "saving"}
          className="h-7 flex-1 bg-transparent text-[13.5px] text-foreground outline-none placeholder:text-muted disabled:opacity-60"
        />
        {value.trim() ? (
          <button
            type="submit"
            disabled={status === "saving"}
            className="rounded-md bg-[var(--color-brand-600)] px-3 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-60"
          >
            {status === "saving" ? "Adding…" : "Add"}
          </button>
        ) : (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={status === "saving"}
              className="rounded-md border border-border bg-surface px-2.5 py-1 text-[12px] text-muted hover:bg-raised hover:text-foreground disabled:opacity-60"
              title="Choose a file to upload"
            >
              Upload file
            </button>
            <button
              type="button"
              onClick={() => folderInputRef.current?.click()}
              disabled={status === "saving"}
              className="rounded-md border border-border bg-surface px-2.5 py-1 text-[12px] text-muted hover:bg-raised hover:text-foreground disabled:opacity-60"
              title="Choose a folder to upload (preserves structure)"
            >
              Upload folder
            </button>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) handleFiles(e.target.files);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
        />
        <input
          ref={folderInputRef}
          type="file"
          multiple
          // Non-standard attrs for directory selection — supported by Chromium
          // and Safari/Firefox. React types don't include them.
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) void handleDirectoryInput(e.target.files);
            if (folderInputRef.current) folderInputRef.current.value = "";
          }}
        />
      </form>
      {statusText && (
        <div className="mt-1 pl-[42px] text-[11.5px] leading-tight">
          <span className={"font-medium " + statusTone}>{statusText}</span>
        </div>
      )}
    </div>
  );
}
