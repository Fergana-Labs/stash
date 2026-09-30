"use client";

import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { rmImportTraces } from "@/lib/api";
import { errorMessage } from "./rm-text";

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

  async function importFiles(files: File[]) {
    if (busy.current) {
      toast.error("Wait for the current import to finish before dropping more files.");
      return;
    }
    busy.current = true;
    let imported = 0;
    try {
      for (const file of files) {
        setUploading(file.name);
        try {
          if (!/\.(json|jsonl|ndjson|txt)$/i.test(file.name)) {
            throw new Error(file.name.toLowerCase().endsWith(".zip")
              ? "Unzip this archive, then drop the trace files inside."
              : "Choose a JSON, JSONL, NDJSON, or text file.");
          }
          const result = await rmImportTraces("auto", await file.text());
          imported += result.imported;
        } catch (error) {
          toast.error(`${file.name}: ${errorMessage(error)}`);
        }
      }
      if (imported > 0) {
        toast.success(`Imported ${imported} trace${imported === 1 ? "" : "s"}`);
        onImported();
      }
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
        void importFiles(Array.from(event.dataTransfer.files));
      }}
    >
      {children}
      {(dragging || uploading) && (
        <div className="pointer-events-none absolute inset-0 z-40 flex flex-col items-center justify-center gap-3 border-2 border-brand-500 bg-background/95 px-8 text-center">
          {uploading ? <Loader2 className="size-6 animate-spin text-muted-foreground" /> : <Upload className="size-6 text-brand-500" />}
          <p role="status" className="m-0 max-w-full truncate text-[15px] font-medium">
            {uploading ? `Importing ${uploading}…` : "Drop files to import traces"}
          </p>
        </div>
      )}
    </div>
  );
}
