"use client";
/* eslint-disable @next/next/no-img-element -- local object URLs of the user's own files. */

import { useEffect, useRef, useState } from "react";
import { FileUp, Loader2, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { readTraceEntries, type TraceFile } from "@/components/reward-models/trace-files";
import { tasteAddExamples } from "@/lib/taste-api";
import { cn } from "@/lib/utils";
import { useWizard } from "../wizard-ui";

const MAX_BYTES = 8_000_000;
const MAX_ITEMS = 40;
const ACCEPT = ".html,.htm,.png,.jpg,.jpeg,.webp";
type Label = "liked" | "disliked";

interface Item {
  key: string;
  file: File;
  html: boolean;
  preview: string; // object URL for images, page source for HTML
  label: Label | null;
}

const isHtml = (name: string) => /\.html?$/i.test(name);
export const usable = (f: File) => !f.name.startsWith(".") && /\.(html?|png|jpe?g|webp)$/i.test(f.name) && f.size <= MAX_BYTES;

async function encode(file: File): Promise<string> {
  if (isHtml(file.name)) return file.text();
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** A small, inert preview: screenshots as images, HTML in a sandboxed frame with scripts off. */
function Preview({ item }: { item: Item }) {
  return (
    <div className="relative aspect-[3/2] overflow-hidden bg-surface">
      {item.html ? (
        <iframe title={item.file.name} sandbox="" srcDoc={item.preview} tabIndex={-1} className="pointer-events-none absolute top-0 left-0 h-[600%] w-[600%] origin-top-left scale-[0.1667] border-0 bg-white" />
      ) : (
        <img src={item.preview} alt={item.file.name} className="h-full w-full object-cover object-top" />
      )}
    </div>
  );
}

/** Contrastive examples: upload pages (HTML or screenshots), then mark each one good or bad. */
export default function ExampleSites({ onDone }: { onDone: (text: string, jobId: string | null) => void }) {
  const { sessionId, send, adoptModel } = useWizard();
  const [items, setItems] = useState<Item[]>([]);
  const [saving, setSaving] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const urls = useRef<string[]>([]);
  useEffect(() => () => urls.current.forEach((u) => URL.revokeObjectURL(u)), []);

  async function add(files: TraceFile[]) {
    const fresh = files.map((f) => f.file).filter(usable);
    const next = await Promise.all(fresh.map(async (file) => {
      const html = isHtml(file.name);
      const preview = html ? await file.text() : URL.createObjectURL(file);
      if (!html) urls.current.push(preview);
      return { key: `${file.name}:${file.size}:${file.lastModified}`, file, html, preview, label: null } as Item;
    }));
    setItems((prev) => [...prev, ...next.filter((n) => !prev.some((p) => p.key === n.key))].slice(0, MAX_ITEMS));
    setError(fresh.length < files.filter((f) => !f.file.name.startsWith(".")).length ? "Some files were skipped: use HTML or PNG/JPEG/WebP, up to 8 MB." : "");
  }

  const setLabel = (key: string, label: Label) => setItems((prev) => prev.map((i) => (i.key === key ? { ...i, label: i.label === label ? null : label } : i)));
  const remove = (key: string) => setItems((prev) => prev.filter((i) => i.key !== key));

  async function save() {
    if (!sessionId) return;
    setSaving(true); setError("");
    try {
      const files = await Promise.all(items.filter((i) => i.label).map(async (i) => ({ name: i.file.name, label: i.label as Label, content: await encode(i.file) })));
      const result = await tasteAddExamples(sessionId, files);
      adoptModel?.(result.model_id);
      const text = `Added ${result.added.liked} good example${result.added.liked === 1 ? "" : "s"} and ${result.added.disliked} bad.`;
      onDone(text, result.job_id);
      send(text, "event");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const good = items.filter((i) => i.label === "liked").length;
  const bad = items.filter((i) => i.label === "disliked").length;
  const unsorted = items.length - good - bad;
  const enough = good >= 2 && bad >= 2;
  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop pages or click to choose files"
        aria-disabled={saving}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault(); setDrag(false);
          const entries = Array.from(e.dataTransfer.items).map((item) => item.webkitGetAsEntry()).filter((x): x is FileSystemEntry => !!x);
          void readTraceEntries(entries).then(add).catch((err) => setError(errorMessage(err)));
        }}
        className={cn("grid cursor-pointer place-items-center gap-1 rounded-md border border-dashed border-border px-4 text-center transition-colors hover:bg-surface/60", items.length ? "py-3" : "py-6", drag && "border-brand-500 bg-brand-500/5", saving && "pointer-events-none opacity-60")}
      >
        {!items.length && <FileUp className="size-5 text-muted-foreground" />}
        <p className="m-0 text-[12.5px]">{items.length ? <>Drop more pages, or <span className="underline">choose files</span></> : <>Drop web pages here, or <span className="underline">choose files</span></>}</p>
        {!items.length && <p className="m-0 text-[11px] text-muted-foreground">HTML pages or screenshots of sites you like and ones you don’t</p>}
      </div>
      <input ref={input} type="file" multiple hidden accept={ACCEPT} aria-label="Choose example pages" onChange={(e) => { const list = e.target.files; if (list?.length) void add(Array.from(list).map((file) => ({ file, path: file.name }))); e.target.value = ""; }} />
      {items.length > 0 && (
        <ul className="m-0 mt-3 grid list-none grid-cols-2 gap-2.5 p-0 sm:grid-cols-4">
          {items.map((item) => (
            <li key={item.key} className={cn("overflow-hidden rounded border", item.label === "liked" ? "border-emerald-500/60" : item.label === "disliked" ? "border-red-500/60" : "border-border")}>
              <Preview item={item} />
              <div className="flex items-center gap-1 border-t border-border px-1.5 py-1">
                <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground" title={item.file.name}>{item.file.name}</span>
                <button type="button" aria-label={`Mark ${item.file.name} good`} aria-pressed={item.label === "liked"} onClick={() => setLabel(item.key, "liked")} className={cn("rounded p-1 hover:bg-surface", item.label === "liked" ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" : "text-muted-foreground")}><ThumbsUp className="size-3.5" /></button>
                <button type="button" aria-label={`Mark ${item.file.name} bad`} aria-pressed={item.label === "disliked"} onClick={() => setLabel(item.key, "disliked")} className={cn("rounded p-1 hover:bg-surface", item.label === "disliked" ? "bg-red-500/15 text-red-700 dark:text-red-400" : "text-muted-foreground")}><ThumbsDown className="size-3.5" /></button>
                <button type="button" aria-label={`Remove ${item.file.name}`} onClick={() => remove(item.key)} className="rounded p-1 text-muted-foreground hover:bg-surface hover:text-foreground"><X className="size-3" /></button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {items.length > 0 && (
        <div className="mt-2 flex items-center gap-2">
          <span className="flex-1 text-[11.5px] text-muted-foreground">
            {good} good · {bad} bad{unsorted ? ` · ${unsorted} not marked` : ""}{!enough && " — mark at least two of each"}
          </span>
          <Button type="button" size="sm" disabled={saving || !enough} onClick={() => void save()}>
            {saving && <Loader2 className="animate-spin" />}{saving ? "Rendering your examples…" : `Use these ${good + bad} examples`}
          </Button>
        </div>
      )}
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
    </div>
  );
}
