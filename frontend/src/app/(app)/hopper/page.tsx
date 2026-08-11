"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { dropHopperFile, dropHopperLink, type HopperDrop } from "@/lib/api";
import { isLinkDrop } from "@/lib/hopper";

/** The hopper is an intake, not a place: a drop lands in the VFS and the
 *  confirmation points there. Nothing accumulates on this page. */
export default function HopperRoute() {
  useBreadcrumbs([{ label: "Hopper" }], "hopper");

  const [dragging, setDragging] = useState(false);
  const [adding, setAdding] = useState(0);
  const [text, setText] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

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

  // Paste works anywhere on the page — a screenshot from the clipboard, a URL,
  // or a wall of text — except while typing in the box, which submits itself.
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
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-8 py-7">
        <header>
          <h1 className="text-[20px] font-semibold text-foreground">Hopper</h1>
          <p className="mt-1 text-[13.5px] text-muted-foreground">
            Drop anything in. It lands in your Stash and your agents can read it — files,
            screenshots, PDFs, web pages.
          </p>
        </header>

        <div
          onClick={() => fileInput.current?.click()}
          className={`cursor-pointer rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors ${
            dragging
              ? "border-brand-500 bg-brand-500/10"
              : "border-border bg-surface hover:border-brand-300"
          }`}
        >
          {adding > 0 ? (
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-brand-600" />
          ) : (
            <Upload className="mx-auto h-6 w-6 text-dim" />
          )}
          <p className="mt-3 text-[14px] font-medium text-foreground">
            {adding > 0
              ? `Adding ${adding} ${adding === 1 ? "item" : "items"}…`
              : "Drag files here, paste a link, or click to browse"}
          </p>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            PDFs, docs, spreadsheets, screenshots, web pages — anything you want your agent to
            know about.
          </p>
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
        </div>

        <form
          className="flex items-start gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            addLink(text);
            setText("");
          }}
        >
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                addLink(text);
                setText("");
              }
            }}
            rows={2}
            placeholder="Paste a link…"
            className="min-h-[52px] flex-1 resize-y rounded-lg border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground outline-none placeholder:text-muted-foreground focus:border-brand-400"
          />
          <Button type="submit" disabled={!text.trim()} className="h-[52px]">
            Add
          </Button>
        </form>
      </div>
    </div>
  );
}
