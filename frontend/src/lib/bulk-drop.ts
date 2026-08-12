/** Reading a drop, and running it. A dropped directory arrives as a tree of
 *  filesystem entries rather than a flat FileList, and eighty files uploaded
 *  one after another take eighty round trips of dead time — so both live here,
 *  away from the component, where they can be tested. */

export type DroppedFile = {
  file: File;
  /** Folder path relative to what was dropped, e.g. ["catalogs", "meritor"]. */
  path: string[];
};

/** How many uploads are in flight at once. Enough to hide latency; not so many
 *  that a large drop saturates the connection or the extraction queue. */
export const UPLOAD_CONCURRENCY = 5;

// Directory listings arrive in batches and the reader must be drained until it
// returns an empty one — a single readEntries call silently truncates at ~100.
async function readAllEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  const all: FileSystemEntry[] = [];
  for (;;) {
    const batch: FileSystemEntry[] = await new Promise((resolve, reject) =>
      reader.readEntries(resolve, reject),
    );
    if (!batch.length) return all;
    all.push(...batch);
  }
}

async function flatten(entries: FileSystemEntry[], prefix: string[]): Promise<DroppedFile[]> {
  const out: DroppedFile[] = [];
  for (const entry of entries) {
    // Dotfiles and dot-directories are tooling residue (.DS_Store, .git,
    // .obsidian); nobody drops a folder meaning to stash those.
    if (entry.name.startsWith(".")) continue;
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) =>
        (entry as FileSystemFileEntry).file(resolve, reject),
      );
      out.push({ file, path: prefix });
    } else if (entry.isDirectory) {
      const children = await readAllEntries((entry as FileSystemDirectoryEntry).createReader());
      out.push(...(await flatten(children, [...prefix, entry.name])));
    }
  }
  return out;
}

/** Every file in a drop, directories walked. Falls back to the flat file list
 *  only when the browser gives us no entries API — the paths are then empty,
 *  which is exactly right for a multi-file (non-folder) drop. */
export async function filesFromDrop(dataTransfer: DataTransfer): Promise<DroppedFile[]> {
  const entries = Array.from(dataTransfer.items ?? [])
    .filter((item) => item.kind === "file")
    .map((item) => item.webkitGetAsEntry?.())
    .filter((entry): entry is FileSystemEntry => !!entry);
  if (entries.length > 0) return flatten(entries, []);
  return Array.from(dataTransfer.files).map((file) => ({ file, path: [] }));
}

/** Files chosen through a picker. A directory picker sets webkitRelativePath,
 *  so choosing a folder mirrors it the same way dropping one does. */
export function filesFromPicker(files: File[]): DroppedFile[] {
  return files
    .filter((file) => !file.name.startsWith("."))
    .map((file) => {
      const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
      const path = relative ? relative.split("/").slice(0, -1) : [];
      return { file, path: path.filter((p) => !p.startsWith(".")) };
    });
}

/** Run `worker` over every item, `limit` at a time, in order of start. Results
 *  keep the input's order. Never rejects: a worker that throws yields its
 *  error, so one bad file cannot abandon the other seventy-nine. */
export async function runPool<T, R>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
  options: { signal?: AbortSignal } = {},
): Promise<Array<{ ok: true; value: R } | { ok: false; error: unknown } | { ok: "skipped" }>> {
  const results = new Array<
    { ok: true; value: R } | { ok: false; error: unknown } | { ok: "skipped" }
  >(items.length);
  let next = 0;

  async function pump(): Promise<void> {
    for (;;) {
      const index = next++;
      if (index >= items.length) return;
      if (options.signal?.aborted) {
        results[index] = { ok: "skipped" };
        continue;
      }
      try {
        results[index] = { ok: true, value: await worker(items[index], index) };
      } catch (error) {
        results[index] = { ok: false, error };
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, pump));
  return results;
}
