"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
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

  const [dragging, setDragging] = useState(false);
  const [adding, setAdding] = useState(0);
  const [link, setLink] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const well = useRef<HTMLDivElement>(null);

  const runDrops = useCallback(async (drops: Array<() => Promise<HopperDrop>>) => {
    setAdding((n) => n + drops.length);
    for (const drop of drops) {
      try {
        const landed = await drop();
        if (landed.kind === "link") {
          toast.success(`Reading ${landed.name}`, { description: "It'll appear in your VFS" });
        } else {
          toast.success(`${landed.name} is in your VFS`);
        }
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Couldn't add that to your Stash");
      } finally {
        setAdding((n) => n - 1);
      }
    }
  }, []);

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

  // The warm light under the cursor is written straight to CSS vars: this
  // fires on every mouse move and must not re-render React.
  function trackCursor(e: React.MouseEvent) {
    const node = well.current;
    if (!node) return;
    const box = node.getBoundingClientRect();
    node.style.setProperty("--hopper-x", `${e.clientX - box.left}px`);
    node.style.setProperty("--hopper-y", `${e.clientY - box.top}px`);
  }

  const live = dragging || adding > 0;

  return (
    // min-h-full, not h-full + overflow: the shell's <main> is the scroll
    // container. The height still spans the pane so a drop anywhere counts.
    <div
      className="min-h-full"
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <div className="mx-auto flex min-h-full max-w-[560px] flex-col justify-center px-8 py-12">
        <header className="mb-8">
          <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
            Intake
          </p>
          <h1 className="mt-2.5 font-display text-[34px] font-semibold leading-[1.05] tracking-[-0.02em] text-foreground">
            Drop anything.
            <br />
            <span className="text-dim">Your agents can read it.</span>
          </h1>
        </header>

        <div
          ref={well}
          onMouseMove={trackCursor}
          onClick={() => fileInput.current?.click()}
          data-live={live}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") fileInput.current?.click();
          }}
          aria-label="Drop files here, or click to browse"
          className="hopper-well relative isolate flex h-[220px] cursor-pointer flex-col items-center justify-center gap-5 overflow-hidden rounded-[20px] outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
        >
          <span className="hopper-grain" aria-hidden />

          {/* The mouth of the port: rings draw inward while a drop is in flight. */}
          <span className="relative flex h-[74px] w-[74px] items-center justify-center" aria-hidden>
            {live &&
              [0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="hopper-ring absolute inset-0 rounded-full border border-brand-400/70"
                />
              ))}
            <span className="absolute inset-[18px] rounded-full border border-[var(--divider-color)]" />
            <ArrowDown
              className={`${live ? "" : "hopper-arrow"} relative h-[18px] w-[18px] ${
                live ? "text-brand-600" : "text-dim"
              }`}
              strokeWidth={1.5}
            />
          </span>

          <div className="relative text-center">
            <p className="font-display text-[15px] font-medium tracking-[-0.01em] text-foreground">
              {adding > 0
                ? `Taking in ${adding} ${adding === 1 ? "item" : "items"}…`
                : dragging
                  ? "Let go"
                  : "Drag in, paste, or click"}
            </p>
            <p className="mt-2 font-mono text-[9.5px] uppercase tracking-[0.18em] text-muted-foreground">
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
          className="mt-7 flex items-center gap-3 border-b border-[var(--divider-color)] pb-2.5 transition-colors focus-within:border-brand-400"
          onSubmit={(e) => {
            e.preventDefault();
            addLink(link);
            setLink("");
          }}
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
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
            className="font-mono text-[10px] uppercase tracking-[0.22em] text-brand-600 transition-opacity disabled:pointer-events-none disabled:opacity-0"
          >
            Take it
          </button>
        </form>
      </div>
    </div>
  );
}
