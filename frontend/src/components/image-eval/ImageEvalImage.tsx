"use client";

import { useEffect, useState } from "react";
import { fetchAuthed } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

/** An owner-only image (example or scored call), fetched with the user's token; click to enlarge. */
export default function ImageEvalImage({ path, alt, className }: { path: string; alt: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    void fetchAuthed(path).then(async (response) => {
      if (!response.ok) throw new Error("Image unavailable");
      const blob = await response.blob();
      if (cancelled) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path]);
  if (!url) {
    return <div className={cn("flex items-center justify-center rounded-md border border-border bg-surface/30 text-[11px] text-muted-foreground", className)} role="status">
      {failed ? "Image unavailable" : "Loading…"}
    </div>;
  }
  return <Dialog>
    <DialogTrigger asChild>
      <button type="button" aria-label={`Enlarge ${alt}`} className={cn("block cursor-zoom-in overflow-hidden rounded-md border border-border bg-white p-0", className)}>
        {/* Authenticated blobs cannot go through the public image optimizer. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt={alt} className="h-full w-full object-contain" />
      </button>
    </DialogTrigger>
    <DialogContent className="w-auto max-w-[95vw] sm:max-w-[95vw]">
      <DialogTitle className="sr-only">{alt}</DialogTitle>
      <DialogDescription className="sr-only">Full-size image</DialogDescription>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt={alt} className="max-h-[85vh] max-w-full object-contain" />
    </DialogContent>
  </Dialog>;
}
