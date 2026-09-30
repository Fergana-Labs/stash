"use client";

import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { errorMessage } from "./rm-text";
import { importTraceFiles, readTraceEntries } from "./trace-files";

export default function TraceDropzone({ children, onImported }: {
  children: ReactNode;
  onImported: () => void;
}) {
  const depth = useRef(0);
  const busy = useRef(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);

  function isFileDrag(event: DragEvent<HTMLDivElement>) {
    return event.currentTarget.contains(event.target as Node)
      && event.dataTransfer.types.includes("Files");
  }

  async function importEntries(entries: (FileSystemEntry | null)[]) {
    if (busy.current) {
      toast.error("Wait for the current import to finish before dropping more files.");
      return;
    }
    busy.current = true;
    setUploading("folder contents");
    try {
      if (entries.some((entry) => entry === null)) {
        throw new Error("Cannot read the dropped item. Select it using Import traces.");
      }
      const files = await readTraceEntries(entries as FileSystemEntry[]);
      const result = await importTraceFiles(files, "auto", setUploading);
      for (const failure of result.failed) toast.error(failure.message);
      if (result.skipped.length > 0) {
        toast.info(`Skipped ${result.skipped.length} supporting file${result.skipped.length === 1 ? "" : "s"}`, {
          description: result.skipped.join(", "),
        });
      }
      if (result.imported > 0) {
        toast.success(`Imported ${result.imported} trace${result.imported === 1 ? "" : "s"}`);
        onImported();
      } else if (result.failed.length === 0) {
        toast.error("No trace files found. Choose JSON, JSONL, NDJSON, or text trace files.");
      }
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      busy.current = false;
      setUploading(null);
    }
  }

  return (
    <div
      role="region"
      aria-label="Trace uploads"
      aria-busy={uploading !== null}
      className="relative h-full"
      onDragEnter={(event) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        depth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = busy.current ? "none" : "copy";
      }}
      onDragLeave={(event) => {
        if (!isFileDrag(event)) return;
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setDragging(false);
      }}
      onDrop={(event) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        depth.current = 0;
        setDragging(false);
        // Capture entries before awaiting: browsers protect the drag data after this event.
        const entries = Array.from(event.dataTransfer.items)
          .filter((item) => item.kind === "file")
          .map((item) => item.webkitGetAsEntry());
        void importEntries(entries);
      }}
    >
      {children}
      {(dragging || uploading) && (
        <div className="pointer-events-none absolute inset-0 z-40 flex flex-col items-center justify-center gap-3 border-2 border-brand-500 bg-background/95 px-8 text-center">
          {uploading ? <Loader2 className="size-6 animate-spin text-muted-foreground" /> : <Upload className="size-6 text-brand-500" />}
          <p role="status" className="m-0 max-w-full truncate text-[15px] font-medium">
            {uploading ? `Importing ${uploading}…` : "Drop files or folders to import traces"}
          </p>
        </div>
      )}
    </div>
  );
}
