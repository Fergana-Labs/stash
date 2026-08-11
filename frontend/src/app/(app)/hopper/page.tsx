"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Check,
  FileText,
  Link2,
  Loader2,
  Puzzle,
  StickyNote,
  Upload,
} from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  dropHopperFile,
  dropHopperLink,
  dropHopperNote,
  listHopper,
  type HopperItem,
  type HopperStatus,
} from "@/lib/api";
import { isLinkDrop, targetHref } from "@/lib/hopper";

// Anything still being read changes on its own, so the feed polls until
// nothing is in flight and then stops.
const POLL_MS = 2500;

const STATUS_LOOK: Record<
  HopperStatus,
  { label: string; className: string; icon: typeof Check; spin?: boolean }
> = {
  legible: {
    label: "Legible",
    className: "text-[var(--color-success)]",
    icon: Check,
  },
  reading: { label: "Reading", className: "text-amber-600", icon: Loader2, spin: true },
  no_text: { label: "No text", className: "text-muted-foreground", icon: AlertTriangle },
  link_only: { label: "Link only", className: "text-amber-600", icon: AlertTriangle },
  needs_extension: { label: "Needs extension", className: "text-amber-600", icon: Puzzle },
  failed: { label: "Failed", className: "text-destructive", icon: AlertTriangle },
};

const KIND_ICON = { file: FileText, link: Link2, note: StickyNote };

function StatusPill({ item }: { item: HopperItem }) {
  const look = STATUS_LOOK[item.status];
  const Icon = look.icon;
  return (
    <span
      title={item.detail}
      className={`flex shrink-0 items-center gap-1.5 text-[12px] font-medium ${look.className}`}
    >
      <Icon className={`h-3.5 w-3.5 ${look.spin ? "animate-spin" : ""}`} />
      {look.label}
    </span>
  );
}

function ItemRow({ item }: { item: HopperItem }) {
  const KindIcon = KIND_ICON[item.kind];
  const href = targetHref(item);
  return (
    <li className="flex items-start gap-3 px-4 py-3.5">
      <KindIcon className="mt-0.5 h-4 w-4 shrink-0 text-dim" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-3">
          <span className="min-w-0 flex-1 truncate text-[13.5px] font-semibold text-foreground">
            {item.label}
          </span>
          <StatusPill item={item} />
        </div>
        {item.preview && (
          // What the agent reads, so "legible" is something you can see rather
          // than a claim you have to trust.
          <p className="mt-1 line-clamp-2 text-[12.5px] leading-relaxed text-dim">
            {item.preview}
          </p>
        )}
        {item.status !== "legible" && item.detail && (
          <p className="mt-1 text-[12.5px] text-muted-foreground">{item.detail}</p>
        )}
        {href && (
          <Link href={href} className="mt-1 inline-block text-[12px] text-brand-700 hover:underline">
            Open {item.target!.name}
          </Link>
        )}
      </div>
    </li>
  );
}

export default function HopperRoute() {
  useBreadcrumbs([{ label: "Hopper" }], "hopper");

  const [items, setItems] = useState<HopperItem[] | null>(null);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [adding, setAdding] = useState(0);
  const [text, setText] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const feed = await listHopper();
      setItems(feed.items);
      setFolderId(feed.folder_id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't load your hopper");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const waiting = (items ?? []).some((i) => i.status === "reading");
  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [waiting, refresh]);

  const runDrops = useCallback(
    async (drops: Array<() => Promise<HopperItem>>) => {
      setAdding((n) => n + drops.length);
      for (const drop of drops) {
        try {
          const item = await drop();
          setItems((current) => [item, ...(current ?? [])]);
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "Couldn't add that to your hopper");
        } finally {
          setAdding((n) => n - 1);
        }
      }
    },
    [],
  );

  const addFiles = useCallback(
    (files: File[]) => void runDrops(files.map((f) => () => dropHopperFile(f))),
    [runDrops],
  );

  const addText = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      void runDrops([() => (isLinkDrop(trimmed) ? dropHopperLink(trimmed) : dropHopperNote(trimmed))]);
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
        addText(pasted);
      }
    }
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [addFiles, addText]);

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
    if (url) addText(url);
  }

  return (
    // min-h-full, not h-full + overflow: the shell's <main> is the scroll
    // container, and a second one here would trap the feed inside it. The
    // height still spans the pane so a drop anywhere on it counts.
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
            screenshots, links, half-formed notes.
          </p>
        </header>

        <div
          onClick={() => fileInput.current?.click()}
          className={`cursor-pointer rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
            dragging
              ? "border-brand-500 bg-brand-500/10"
              : "border-border bg-surface hover:border-brand-300"
          }`}
        >
          <Upload className="mx-auto h-6 w-6 text-dim" />
          <p className="mt-3 text-[14px] font-medium text-foreground">
            Drag files here, paste a link, or click to browse
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
            addText(text);
            setText("");
          }}
        >
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                addText(text);
                setText("");
              }
            }}
            rows={2}
            placeholder="Paste a link, or type a note…"
            className="min-h-[52px] flex-1 resize-y rounded-lg border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground outline-none placeholder:text-muted-foreground focus:border-brand-400"
          />
          <Button type="submit" disabled={!text.trim()} className="h-[52px]">
            Add
          </Button>
        </form>

        <section>
          <div className="flex items-baseline justify-between">
            <h2 className="text-[15px] font-semibold text-foreground">In the hopper</h2>
            {folderId && (
              <Link
                href={`/folders/${folderId}`}
                className="text-[12px] text-brand-700 hover:underline"
              >
                Browse the Hopper folder in your VFS
              </Link>
            )}
          </div>

          <div className="mt-3 overflow-hidden rounded-xl border border-border bg-surface">
            {adding > 0 && (
              <div className="flex items-center gap-2 border-b border-border px-4 py-3 text-[13px] text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Adding {adding} {adding === 1 ? "item" : "items"}…
              </div>
            )}
            {items === null ? (
              <div className="flex flex-col gap-2 p-4">
                {Array.from({ length: 3 }, (_, i) => (
                  <Skeleton key={i} className="h-[46px] rounded-lg" />
                ))}
              </div>
            ) : items.length === 0 && adding === 0 ? (
              <p className="px-4 py-8 text-center text-[13px] text-muted-foreground">
                Nothing yet. The first thing you drop shows up here the moment your agent can
                read it.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {items.map((item) => (
                  <ItemRow key={item.id} item={item} />
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
