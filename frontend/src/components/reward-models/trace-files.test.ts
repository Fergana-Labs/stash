import { beforeEach, expect, it, vi } from "vitest";
import { rmImportTraces } from "@/lib/api";
import { importTraceFiles, readTraceEntries } from "./trace-files";

vi.mock("@/lib/api", () => ({ rmImportTraces: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

function entry(path: string, text: string): FileSystemEntry {
  const file = Object.assign(new File([text], path.split("/").at(-1)!), { text: async () => text });
  return { isFile: true, fullPath: path, file: (resolve: (file: File) => void) => resolve(file) } as FileSystemFileEntry;
}

function folder(path: string, batches: FileSystemEntry[][]): FileSystemEntry {
  return {
    isDirectory: true, fullPath: path,
    createReader: () => {
      let index = 0;
      return { readEntries: (resolve: (entries: FileSystemEntry[]) => void) => resolve(index < batches.length ? batches[index++] : []) };
    },
  } as FileSystemDirectoryEntry;
}

it("reads every directory batch and preserves nested paths instead of truncating large folders", async () => {
  const files = await readTraceEntries([folder("/bundle", [
    [entry("/bundle/first.json", "first")],
    [folder("/bundle/nested", [[entry("/bundle/nested/last.jsonl", "last")]])],
  ])]);
  expect(files.map((file) => file.path)).toEqual(["bundle/first.json", "bundle/nested/last.jsonl"]);
});

it("imports a trace bundle while reporting its manifest, guide, and hidden files as skipped", async () => {
  vi.mocked(rmImportTraces).mockResolvedValue({ imported: 13, format: "stash", trace_ids: [] });
  const files = await readTraceEntries([
    entry("/bundle/traces.jsonl", "traces"), entry("/bundle/manifest.json", "metadata"),
    entry("/bundle/START-HERE.md", "guide"), entry("/bundle/.private/config.json", "private"),
  ]);
  const result = await importTraceFiles(files, "auto", vi.fn());
  expect(rmImportTraces).toHaveBeenCalledExactlyOnceWith("auto", "traces");
  expect(result.imported).toBe(13);
  expect(result.failed).toEqual([]);
  expect(result.skipped).toEqual(["bundle/manifest.json", "bundle/START-HERE.md", "bundle/.private/config.json"]);
});

it("reports unreadable folders instead of silently importing incomplete contents", async () => {
  const unreadable = {
    isDirectory: true, fullPath: "/private",
    createReader: () => ({ readEntries: (_resolve: unknown, reject: (error: Error) => void) => reject(new Error("Access denied")) }),
  } as unknown as FileSystemDirectoryEntry;
  await expect(readTraceEntries([unreadable])).rejects.toThrow("Access denied");
  expect(rmImportTraces).not.toHaveBeenCalled();
});
