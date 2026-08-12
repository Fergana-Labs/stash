"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { dropHopperFile, dropHopperLink } from "@/lib/api";
import { isLinkDrop } from "@/lib/hopper";
import {
  filesFromDrop,
  filesFromPicker,
  runPool,
  UPLOAD_CONCURRENCY,
  type DroppedFile,
} from "@/lib/bulk-drop";

// Machine-facing facts, set in mono: what the well accepts. Space does the
// separating — middots between caps is the house style of every AI landing
// page this year.
const ACCEPTS = ["PDF", "DOCX", "XLSX", "PPTX", "CSV", "MD", "PNG", "JPG", "URL"];

type Batch = {
  total: number;
  done: number;
  skipped: number;
  failed: Array<{ name: string; reason: string }>;
  cancel: AbortController;
};

function summarise(batch: Batch): string {
  const parts = [`${batch.done} added`];
  if (batch.skipped) parts.push(`${batch.skipped} already there`);
  if (batch.failed.length) parts.push(`${batch.failed.length} failed`);
  return parts.join(" · ");
}

/** The hopper is an intake, not a place: a drop lands in the VFS and the
 *  confirmation points there. Nothing accumulates on this page. */
export default function HopperRoute() {
  useBreadcrumbs([{ label: "Hopper" }], "hopper");
  const router = useRouter();

  const [dragging, setDragging] = useState(false);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [link, setLink] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  // A single drop confirms itself; a batch reports once at the end. Eighty
  // toasts for eighty files is not a confirmation, it is a denial of service.
  const addFiles = useCallback(
    async (dropped: DroppedFile[]) => {
      if (dropped.length === 0) return;
      const cancel = new AbortController();
      const live: Batch = { total: dropped.length, done: 0, skipped: 0, failed: [], cancel };
      setBatch(live);

      const results = await runPool(
        dropped,
        UPLOAD_CONCURRENCY,
        async ({ file, path }) => {
          const landed = await dropHopperFile(file, { path, signal: cancel.signal });
          if (landed.duplicate) live.skipped += 1;
          else live.done += 1;
          setBatch({ ...live });
          return landed;
        },
        { signal: cancel.signal },
      );

      results.forEach((result, i) => {
        if (result.ok === false) {
          const error = result.error;
          live.failed.push({
            name: dropped[i].file.name,
            reason: error instanceof Error ? error.message : "Upload failed",
          });
        }
      });
      setBatch(null);

      if (cancel.signal.aborted) {
        toast.info(`Stopped — ${summarise(live)}`);
        return;
      }
      // One file keeps its own confirmation: naming it and offering the way to
      // it is more useful than a count of one.
      const only = results.length === 1 && results[0].ok === true ? results[0].value : null;
      if (only) {
        toast.success(
          only.duplicate ? `${only.name} was already in your Stash` : `${only.name} is in your Stash`,
          {
            action: {
              label: only.kind === "page" ? "Go to page" : "Go to file",
              onClick: () => router.push(`/${only.kind === "page" ? "p" : "f"}/${only.id}`),
            },
          },
        );
        return;
      }
      toast.success(summarise(live), {
        description: live.failed.length
          ? live.failed
              .slice(0, 3)
              .map((f) => f.name)
              .join(", ")
          : "They'll be readable as your agent finishes reading them",
        action: { label: "Go to VFS", onClick: () => router.push("/files") },
      });
    },
    [router],
  );

  // The hopper takes things that already exist, so text is only ever a link.
  const addLink = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      if (!isLinkDrop(trimmed)) {
        toast.error("That isn't a link", { description: "Drop a file, or paste a URL" });
        return;
      }
      try {
        await dropHopperLink(trimmed);
        // The page is fetched by a worker and filed under Clips when it
        // arrives, so there is nothing to go to yet.
        toast.success("Fetching that page", { description: "It'll land in Clips" });
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Couldn't add that to your Stash");
      }
    },
    [],
  );

  // Paste works anywhere on the page — a screenshot from the clipboard or a
  // URL — except while typing in the link field, which submits itself.
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target?.tagName === "TEXTAREA" || target?.tagName === "INPUT") return;
      const files = Array.from(e.clipboardData?.files ?? []);
      if (files.length > 0) {
        e.preventDefault();
        void addFiles(files.map((file) => ({ file, path: [] })));
        return;
      }
      const pasted = e.clipboardData?.getData("text/plain") ?? "";
      if (pasted.trim()) {
        e.preventDefault();
        void addLink(pasted);
      }
    }
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [addFiles, addLink]);

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    // Read the drop before awaiting anything: the DataTransfer is emptied by
    // the browser as soon as the event handler yields.
    const dropped = await filesFromDrop(e.dataTransfer);
    if (dropped.length > 0) {
      void addFiles(dropped);
      return;
    }
    // Dragging a link out of a browser tab hands over its URL, not a file.
    const url = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
    if (url) void addLink(url);
  }

  const live = dragging || batch !== null;

  return (
    // min-h-full, not h-full + overflow: the shell's <main> is the scroll
    // container. The height still spans the pane so a drop anywhere counts.
    <div
      className="flex min-h-full flex-col"
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <div className="mx-auto flex w-full max-w-[1100px] flex-1 flex-col px-10 py-10">
        <header className="mb-7 shrink-0">
          <h1 className="font-display text-[32px] font-bold leading-[1.1] tracking-[-0.02em] text-foreground">
            Drop anything into your Stash
          </h1>
        </header>

        <div
          onClick={() => fileInput.current?.click()}
          data-live={live}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") fileInput.current?.click();
          }}
          aria-label="Drop files here, or click to browse"
          className="hopper-well relative isolate flex min-h-[300px] flex-1 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
        >
          <div className="relative text-center">
            <p className="font-display text-[21px] font-medium tracking-[-0.015em] text-foreground">
              {batch
                ? `Taking in ${batch.done + batch.skipped} of ${batch.total}…`
                : dragging
                  ? "Let go"
                  : "Drag in, paste, or click"}
            </p>
            {batch ? (
              // Progress is a live count and a way out, and it exists only
              // while the batch does — this page keeps no history.
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  batch.cancel.abort();
                }}
                className="mt-3 font-mono text-[11px] uppercase tracking-[0.05em] text-brand-600 hover:underline"
              >
                Stop
              </button>
            ) : (
              <p className="mt-3 flex flex-wrap justify-center gap-x-5 gap-y-1 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
                {ACCEPTS.map((format) => (
                  <span key={format}>{format}</span>
                ))}
              </p>
            )}
          </div>
        </div>

        <input
          ref={fileInput}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            void addFiles(filesFromPicker(Array.from(e.target.files ?? [])));
            e.target.value = "";
          }}
        />

        {/* A hairline, not a box: the link field is the well's understudy. */}
        <form
          className="mt-6 flex shrink-0 items-center gap-3 border-b border-[var(--divider-color)] pb-2.5 transition-colors focus-within:border-brand-400"
          onSubmit={(e) => {
            e.preventDefault();
            void addLink(link);
            setLink("");
          }}
        >
          <span className="font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
            URL
          </span>
          <input
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder="https://"
            className="min-w-0 flex-1 bg-transparent font-mono text-[12.5px] text-foreground caret-brand-500 outline-none placeholder:text-muted-foreground"
          />
          <button
            type="submit"
            disabled={!link.trim()}
            className="font-mono text-[11px] uppercase tracking-[0.05em] text-brand-600 transition-opacity disabled:pointer-events-none disabled:opacity-0"
          >
            Take it
          </button>
        </form>
      </div>
    </div>
  );
}
