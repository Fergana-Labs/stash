"use client";

import { useState } from "react";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { droppedFiles } from "./dropped-files";

/** A drop zone for examples: images, PDFs and text or code files, or folders of them. */
export default function UploadBox({ title, hint, compact, disabled, onFiles }: { title: string; hint?: string; compact?: boolean; disabled: boolean; onFiles: (files: File[]) => void }) {
  const [over, setOver] = useState(false);
  const send = (files: File[]) => { if (files.length) onFiles(files); };
  return <label onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
    onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) void droppedFiles(e.dataTransfer).then(send); }}
    className={cn("cursor-pointer items-center justify-center rounded border text-center transition-colors", compact ? "inline-flex px-2 py-0.5" : "flex w-full flex-col gap-2 bg-surface/40 px-4 py-10 hover:bg-surface/70 sm:py-14",
      over ? "border-brand-500 bg-brand-500/5" : "border-border hover:border-foreground/25", disabled && "cursor-not-allowed opacity-60")}>
    {!compact && <span className="flex size-9 items-center justify-center rounded-full border border-border bg-background text-muted-foreground"><Upload className="size-4" /></span>}
    <span className={compact ? "text-[12px]" : "text-[14px] font-medium"}>{title}</span>
    {!compact && <span className="text-[12px] text-muted-foreground">{hint ?? "Drag files or a folder here, or click to choose. Images, PDFs, text and code."}</span>}
    <input type="file" multiple className="sr-only" disabled={disabled} onChange={(e) => { send(Array.from(e.target.files ?? [])); e.target.value = ""; }} aria-label={title} />
  </label>;
}
