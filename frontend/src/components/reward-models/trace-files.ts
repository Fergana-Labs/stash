import { rmImportTraces } from "@/lib/api";
import { errorMessage } from "./rm-text";

export type TraceFile = { file: File; path: string };
export type FileImportResult = {
  imported: number;
  failed: { entry: TraceFile; message: string }[];
  skipped: string[];
};

export async function readTraceEntries(entries: FileSystemEntry[]): Promise<TraceFile[]> {
  const files: TraceFile[] = [];
  for (const entry of entries) {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => {
        (entry as FileSystemFileEntry).file(resolve, reject);
      });
      files.push({ file, path: entry.fullPath.slice(1) });
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      // Directory readers return batches, not necessarily all children at once.
      for (;;) {
        const children = await new Promise<FileSystemEntry[]>((resolve, reject) => {
          reader.readEntries(resolve, reject);
        });
        if (children.length === 0) break;
        files.push(...await readTraceEntries(children));
      }
    } else {
      throw new Error(`Cannot read ${entry.fullPath}`);
    }
  }
  return files;
}

export async function importTraceFiles(
  files: TraceFile[],
  format: string,
  onProgress: (path: string) => void,
): Promise<FileImportResult> {
  const result: FileImportResult = { imported: 0, failed: [], skipped: [] };
  for (const entry of files) {
    const { file, path } = entry;
    const hidden = path.split("/").some((part) => part.startsWith("."));
    const supported = /\.(json|jsonl|ndjson|txt)$/i.test(file.name);
    const archive = file.name.toLowerCase().endsWith(".zip");
    if (hidden || file.name.toLowerCase() === "manifest.json" || (!supported && !archive)) {
      result.skipped.push(path);
      continue;
    }
    onProgress(path);
    try {
      if (archive) {
        throw new Error("Unzip this archive, then import the folder inside.");
      }
      const imported = await rmImportTraces(format, await file.text());
      result.imported += imported.imported;
    } catch (error) {
      result.failed.push({ entry, message: `${path}: ${errorMessage(error)}` });
    }
  }
  return result;
}
