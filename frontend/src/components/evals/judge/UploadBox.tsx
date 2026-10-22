"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { droppedFiles } from "./dropped-files";

/** A drop zone for examples: images, PDFs and text or code files, or folders of them. */
export default function UploadBox({ title, hint, disabled, onFiles }: { title: string; hint?: string; disabled: boolean; onFiles: (files: File[]) => void }) {
  const [over, setOver] = useState(false);
  const send = (files: File[]) => { if (files.length) onFiles(files); };
  return <label onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
    onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) void droppedFiles(e.dataTransfer).then(send); }}
    className={cn("flex cursor-pointer flex-col items-center justify-center gap-1 rounded border-2 border-dashed px-4 py-10 text-center", over ? "border-brand-500 bg-brand-500/5" : "border-border", disabled && "cursor-not-allowed opacity-60")}>
    <span className="text-[15px] font-medium">{title}</span>
    <span className="text-[12px] text-muted-foreground">{hint ?? "Images, PDFs, text, code"}</span>
    <input type="file" multiple className="sr-only" disabled={disabled} onChange={(e) => { send(Array.from(e.target.files ?? [])); e.target.value = ""; }} aria-label={title} />
  </label>;
}
