"use client";

import { useRef, useState } from "react";
import { FolderOpen, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { readTraceEntries, type TraceFile } from "@/components/reward-models/trace-files";
import { tasteAddExamples } from "@/lib/taste-api";
import { cn } from "@/lib/utils";
import { useWizard } from "../wizard-ui";

const MAX_BYTES = 8_000_000;
const MAX_PER_LABEL = 20;
type Label = "liked" | "disliked";
const GOOD = new Set(["good", "like", "liked", "likes"]);
const BAD = new Set(["bad", "dislike", "disliked", "dislikes"]);

/** The label of the nearest folder named good or bad (or like / dislike) on the file's path. */
export function labelFor(path: string): Label | null {
  for (const part of path.split("/").slice(0, -1).reverse()) {
    const name = part.toLowerCase();
    if (GOOD.has(name)) return "liked";
    if (BAD.has(name)) return "disliked";
  }
  return null;
}

export function sortExamples(files: TraceFile[]) {
  const picked: Record<Label, TraceFile[]> = { liked: [], disliked: [] };
  const skipped: string[] = [];
  for (const entry of files) {
    if (entry.file.name.startsWith(".")) continue;
    const label = labelFor(entry.path);
    const usable = /\.(html?|png|jpe?g|webp)$/i.test(entry.file.name) && entry.file.size <= MAX_BYTES;
    if (label && usable) picked[label].push(entry);
    else skipped.push(entry.path);
  }
  return { picked: { liked: picked.liked.slice(0, MAX_PER_LABEL), disliked: picked.disliked.slice(0, MAX_PER_LABEL) }, skipped };
}

async function encode(file: File): Promise<string> {
  if (/\.html?$/i.test(file.name)) return file.text();
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

const fromList = (list: FileList): TraceFile[] => Array.from(list).map((file) => ({ file, path: file.webkitRelativePath || file.name }));

/** Contrastive examples: one folder holding good/ and bad/ example pages (HTML or screenshots). */
export default function ExampleSites({ onDone }: { onDone: (text: string, jobId: string | null) => void }) {
  const { sessionId, send, adoptModel } = useWizard();
  const [picked, setPicked] = useState<Record<Label, TraceFile[]> | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState("");
  const folder = useRef<HTMLInputElement>(null);

  // Picks add up, so good/ and bad/ can be chosen one at a time. Same path = same file.
  const take = (files: TraceFile[]) => {
    const sorted = sortExamples(files);
    const merge = (a: TraceFile[], b: TraceFile[]) => [...a.filter((x) => !b.some((y) => y.path === x.path)), ...b].slice(0, MAX_PER_LABEL);
    setPicked((prev) => ({ liked: merge(prev?.liked ?? [], sorted.picked.liked), disliked: merge(prev?.disliked ?? [], sorted.picked.disliked) }));
    setSkipped((prev) => [...new Set([...prev, ...sorted.skipped])]);
    setError("");
  };

  async function save() {
    if (!sessionId || !picked) return;
    setSaving(true); setError("");
    try {
      const files = await Promise.all((["liked", "disliked"] as const).flatMap((label) => picked[label].map(async ({ file }) => ({ name: file.name, label, content: await encode(file) }))));
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

  const good = picked?.liked.length ?? 0;
  const bad = picked?.disliked.length ?? 0;
  const enough = good >= 2 && bad >= 2;
  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop a folder with good and bad examples, or click to choose one"
        aria-disabled={saving}
        onClick={() => folder.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") folder.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault(); setDrag(false);
          const entries = Array.from(e.dataTransfer.items).map((item) => item.webkitGetAsEntry()).filter((x): x is FileSystemEntry => !!x);
          void readTraceEntries(entries).then(take).catch((err) => setError(errorMessage(err)));
        }}
        className={cn("grid cursor-pointer place-items-center gap-1 rounded-md border border-dashed border-border px-4 py-6 text-center transition-colors hover:bg-surface/60", drag && "border-brand-500 bg-brand-500/5", saving && "pointer-events-none opacity-60")}
      >
        {saving ? <Loader2 className="size-5 animate-spin text-muted-foreground" /> : <FolderOpen className="size-5 text-muted-foreground" />}
        <p className="m-0 text-[12.5px]">{saving ? "Rendering your examples…" : <>Drop a folder with <code>good/</code> and <code>bad/</code> inside, or <span className="underline">choose one</span></>}</p>
        <p className="m-0 text-[11px] text-muted-foreground">HTML pages or screenshots · at least two of each</p>
      </div>
      {/* webkitdirectory is not in React's input attribute types. */}
      <input ref={folder} type="file" hidden aria-label="Choose a folder of examples" {...{ webkitdirectory: "" }} onChange={(e) => { if (e.target.files?.length) take(fromList(e.target.files)); e.target.value = ""; }} />
      {picked && (
        <div className="mt-2 grid grid-cols-2 gap-3 text-[11.5px]">
          {(["liked", "disliked"] as const).map((label) => (
            <div key={label} className="min-w-0">
              <div className="mb-0.5 font-medium">{label === "liked" ? "Good" : "Bad"} · {picked[label].length}</div>
              <ul className="m-0 list-none space-y-0.5 p-0 text-muted-foreground">
                {picked[label].map((f) => <li key={f.path} className="truncate">{f.file.name}</li>)}
              </ul>
            </div>
          ))}
        </div>
      )}
      {picked && (
        <div className="mt-2 flex items-center gap-2">
          <span className="flex-1 text-[11.5px] text-muted-foreground">
            {!enough ? (good ? "Now add your bad/ folder (at least two)." : bad ? "Now add your good/ folder (at least two)." : "Need at least two good and two bad, in folders named good and bad.") : skipped.length ? `Skipped ${skipped.length} file${skipped.length === 1 ? "" : "s"} outside good/ and bad/.` : ""}
          </span>
          <Button type="button" size="sm" variant="ghost" disabled={saving} onClick={() => { setPicked(null); setSkipped([]); }}>Clear</Button>
          <Button type="button" size="sm" disabled={saving || !enough} onClick={() => void save()}>
            {saving && <Loader2 className="animate-spin" />}Use these {good + bad} examples
          </Button>
        </div>
      )}
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
    </div>
  );
}
