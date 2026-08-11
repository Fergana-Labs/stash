"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { dropHopperFile, dropHopperLink, type HopperDrop } from "@/lib/api";
import { isLinkDrop } from "@/lib/hopper";

// Machine-facing facts, set in mono: what the port accepts. Deliberately terse
// — the well says "drop", this says "of what".
const ACCEPTS = "PDF · DOCX · XLSX · PPTX · CSV · MD · PNG · JPG · URL";

/** The hopper is an intake, not a place: a drop lands in the VFS and the
 *  confirmation points there. Nothing accumulates on this page. */
export default function HopperRoute() {
  useBreadcrumbs([{ label: "Hopper" }], "hopper");
  const router = useRouter();

  const [dragging, setDragging] = useState(false);
  const [adding, setAdding] = useState(0);
  const [link, setLink] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  // A drop that vanishes without saying where it went is worse than no drop
  // at all, so every confirmation names the destination and opens it.
  const runDrops = useCallback(
    async (drops: Array<() => Promise<HopperDrop>>) => {
      setAdding((n) => n + drops.length);
      for (const drop of drops) {
        try {
          const landed = await drop();
          if (landed.kind === "link") {
            // The page is fetched by a worker and filed under Clips when it
            // arrives, so there is nothing to go to yet.
            toast.success("Fetching that page", { description: "It'll land in Clips" });
          } else {
            // One line and one way out. Naming the path as well was a third
            // thing to read on the way to the only thing you'd click.
            toast.success(`${landed.name} is in your Stash`, {
              action: {
                label: landed.kind === "page" ? "Go to page" : "Go to file",
                onClick: () => router.push(`/${landed.kind === "page" ? "p" : "f"}/${landed.id}`),
              },
            });
          }
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "Couldn't add that to your Stash");
        } finally {
          setAdding((n) => n - 1);
        }
      }
    },
    [router],
  );

  const addFiles = useCallback(
    (files: File[]) => void runDrops(files.map((f) => () => dropHopperFile(f))),
    [runDrops],
  );

  // The hopper takes things that already exist, so text is only ever a link.
  const addLink = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      if (!isLinkDrop(trimmed)) {
        toast.error("That isn't a link", { description: "Drop a file, or paste a URL" });
        return;
      }
      void runDrops([() => dropHopperLink(trimmed)]);
    },
    [runDrops],
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
        addFiles(files);
        return;
      }
      const pasted = e.clipboardData?.getData("text/plain") ?? "";
      if (pasted.trim()) {
        e.preventDefault();
        addLink(pasted);
      }
    }
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [addFiles, addLink]);

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      addFiles(files);
      return;
    }
    // Dragging a link out of a browser tab hands over its URL, not a file.
    const url = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
    if (url) addLink(url);
  }

  const live = dragging || adding > 0;

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
              {adding > 0
                ? `Taking in ${adding} ${adding === 1 ? "item" : "items"}…`
                : dragging
                  ? "Let go"
                  : "Drag in, paste, or click"}
            </p>
            <p className="mt-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
              {ACCEPTS}
            </p>
          </div>
        </div>

        <input
          ref={fileInput}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            addFiles(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />

        {/* A hairline, not a box: the link field is the well's understudy. */}
        <form
          className="mt-6 shrink-0 flex items-center gap-3 border-b border-[var(--divider-color)] pb-2.5 transition-colors focus-within:border-brand-400"
          onSubmit={(e) => {
            e.preventDefault();
            addLink(link);
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
