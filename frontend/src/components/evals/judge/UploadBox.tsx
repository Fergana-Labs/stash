"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/** A drop zone for examples: images, PDFs and text or code files. */
export default function UploadBox({ title, hint, disabled, onFiles }: { title: string; hint?: string; disabled: boolean; onFiles: (files: File[]) => void }) {
  const [over, setOver] = useState(false);
  const pick = (list: FileList | null) => { const files = Array.from(list ?? []); if (files.length) onFiles(files); };
  return <label onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
    onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) pick(e.dataTransfer.files); }}
    className={cn("flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed px-4 py-10 text-center", over ? "border-brand-500 bg-brand-500/5" : "border-border", disabled && "cursor-not-allowed opacity-60")}>
    <span className="text-[15px] font-medium">{title}</span>
    <span className="text-[12px] text-muted-foreground">{hint ?? "Drop files here or click to choose: images, PDFs, text or code"}</span>
    <input type="file" multiple className="sr-only" disabled={disabled} onChange={(e) => { pick(e.target.files); e.target.value = ""; }} aria-label={title} />
  </label>;
}
