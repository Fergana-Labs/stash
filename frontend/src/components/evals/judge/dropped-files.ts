/** The files in a drop, with folders opened (recursively). Hidden files such as .DS_Store
 * are skipped. A dropped folder otherwise arrives as one empty file that can't be uploaded. */
export async function droppedFiles(data: DataTransfer): Promise<File[]> {
  // Entries must be taken synchronously, before the first await, while the drop is live.
  const entries = Array.from(data.items ?? [])
    .map((item) => (item.kind === "file" ? item.webkitGetAsEntry?.() : null))
    .filter((entry): entry is FileSystemEntry => !!entry);
  if (!entries.length) return Array.from(data.files ?? []);
  return (await Promise.all(entries.map(filesIn))).flat();
}

async function filesIn(entry: FileSystemEntry): Promise<File[]> {
  if (entry.name.startsWith(".")) return [];
  if (entry.isFile) {
    return [await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject))];
  }
  if (!entry.isDirectory) return [];
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const children: FileSystemEntry[] = [];
  // readEntries returns the folder in batches; an empty batch means it's done.
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    if (!batch.length) break;
    children.push(...batch);
  }
  return (await Promise.all(children.map(filesIn))).flat();
}
