"use client";

import { useRef, useState, type ReactNode } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { evalAddExamples, evalReadFile, type NewExample } from "@/lib/intuition-api";
import { errorMessage } from "@/components/reward-models/rm-text";

const ACCEPT = ".txt,.md,.json,.jsonl,.ndjson,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp,.gif";
const MAX_FILES = 100;

export async function droppedFiles(data: DataTransfer): Promise<File[]> {
  const files: File[] = [];
  let visited = 0;
  async function visit(entry: FileSystemEntry, depth = 0): Promise<void> {
    if (entry.name.startsWith(".")) return;
    if (++visited > 1000 || depth > 16) throw new Error("Choose a smaller folder with fewer subfolders.");
    if (entry.isFile) {
      files.push(await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject)));
      if (files.length > MAX_FILES) throw new Error("Choose up to 100 files at a time.");
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const entries = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
        if (!entries.length) break;
        for (const child of entries) await visit(child, depth + 1);
      }
    }
  }
  if (data.items?.length) {
    const handles = Array.from(data.items).map((item) => ({ entry: item.webkitGetAsEntry?.(), file: item.getAsFile() }));
    for (const { entry, file } of handles) {
      if (entry) await visit(entry);
      else if (file) files.push(file);
    }
  } else files.push(...Array.from(data.files));
  return files;
}

export default function BulkExamples({ id, onAdded, children }: { id: string; onAdded: () => Promise<void>; children?: ReactNode }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [failed, setFailed] = useState<File[]>([]);
  const uploading = useRef(false);
  async function upload(files: File[]) {
    if (!files.length || uploading.current) return;
    setErrors([]); setFailed([]);
    if (files.length > MAX_FILES || files.reduce((sum, file) => sum + file.size, 0) > 20 * 1024 * 1024) {
      setErrors(["Choose up to 100 files, totaling 20 MB or less."]); return;
    }
    setBusy(true);
    uploading.current = true;
    const examples: NewExample[] = [], retry: File[] = [], messages: string[] = [];
    try {
      for (let index = 0; index < files.length; index++) {
        const file = files[index];
        setStatus(`Reading ${index + 1} of ${files.length} files…`);
        try {
          if (!file.size || file.size > 2 * 1024 * 1024) throw new Error("Use a nonempty file smaller than 2 MB");
          examples.push({ item: await evalReadFile(file), label: null, needs_review: true, note: "" });
        } catch (e) { retry.push(file); messages.push(`${file.name}: ${errorMessage(e)}`); }
      }
      if (examples.length) {
        setStatus(`Adding ${examples.length} examples…`);
        await evalAddExamples(id, examples);
        await onAdded();
      }
      setStatus(`${examples.length} example${examples.length === 1 ? "" : "s"} added`);
    } catch (e) { messages.push(errorMessage(e)); setStatus("Could not finish adding examples"); }
    finally { setFailed(retry); setErrors(messages); setBusy(false); uploading.current = false; }
  }
  return <div aria-label="Bulk examples" className={dragging ? "bg-primary/5" : ""} onDragOver={(event) => { if (!Array.from(event.dataTransfer.types ?? []).includes("Files")) return; event.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }} onDrop={(event) => {
    if (!Array.from(event.dataTransfer.types ?? []).includes("Files")) return;
    event.preventDefault(); setDragging(false); if (busy) return;
    void droppedFiles(event.dataTransfer).then(upload).catch((e) => setErrors([errorMessage(e)]));
  }}>
    <div className="border-t border-border bg-surface/20 px-4 py-3">
    <div className="flex flex-wrap items-center gap-3 text-xs"><Upload className="size-3.5 text-muted-foreground" /><span className="mr-auto text-muted-foreground">Drop files or a folder</span><Button size="xs" variant="outline" disabled={busy} onClick={() => fileInput.current?.click()}>Choose files</Button><Button size="xs" variant="outline" disabled={busy} onClick={() => folderInput.current?.click()}>Choose folder</Button></div>
    <input ref={fileInput} aria-label="Bulk files" type="file" multiple accept={ACCEPT} className="hidden" disabled={busy} onChange={(event) => { const files = Array.from(event.target.files ?? []); event.target.value = ""; void upload(files); }} />
    <input ref={(node) => { folderInput.current = node; node?.setAttribute("webkitdirectory", ""); }} aria-label="Example folder" type="file" multiple className="hidden" disabled={busy} onChange={(event) => { const files = Array.from(event.target.files ?? []).filter((file) => !file.webkitRelativePath.split("/").some((part) => part.startsWith("."))); event.target.value = ""; void upload(files); }} />
    {status && <p role="status" className="mt-2 text-xs text-muted-foreground">{status}</p>}
    {!!errors.length && <div role="alert" className="mt-2 space-y-1 text-xs text-destructive">{errors.map((error, index) => <p key={index}>{error}</p>)}</div>}
    {!!failed.length && <Button size="xs" variant="outline" className="mt-2" disabled={busy} onClick={() => void upload(failed)}>Retry failed files</Button>}
    </div>{children}
  </div>;
}
