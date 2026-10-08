"use client";

import { useEffect, useRef, useState } from "react";
import { fetchAuthed } from "@/lib/api";
import type { RmTraceImage } from "@/lib/types";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export default function TraceInlineImage({ image }: { image: RmTraceImage }) {
  const frame = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { setVisible(true); observer.disconnect(); }
    }, { rootMargin: "300px" });
    observer.observe(frame.current!);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    void fetchAuthed(`/api/v1/rm/trace-images/${image.id}`).then(async (response) => {
      if (!response.ok) throw new Error("Image unavailable");
      const blob = await response.blob();
      if (cancelled) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [image.id, visible]);
  return <div ref={frame} className="my-2">
    {url ? <Dialog>
      <DialogTrigger asChild>
        <button type="button" aria-label="Enlarge attached image" className="block max-w-full cursor-zoom-in rounded-md border border-border bg-surface/30 p-0.5">
          {/* Authenticated blobs cannot go through the public image optimizer. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url} alt="Attached image" width={image.width} height={image.height} className="m-0! max-h-56 w-auto max-w-full object-contain" onError={() => { setFailed(true); setUrl(null); }} />
        </button>
      </DialogTrigger>
      <DialogContent className="w-auto max-w-[95vw] sm:max-w-[95vw]">
        <DialogTitle className="sr-only">Attached image</DialogTitle>
        <DialogDescription className="sr-only">Full-size image from this trace.</DialogDescription>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt="Full-size attached image" className="max-h-[85vh] max-w-full object-contain" />
      </DialogContent>
    </Dialog> : <div className="flex h-24 w-48 max-w-full items-center justify-center rounded-md border border-border bg-surface/30 text-xs text-muted-foreground" role="status">
      {failed ? "Image unavailable" : "Loading image…"}
    </div>}
  </div>;
}
