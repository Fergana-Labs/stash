"use client";

import { useRef, useState } from "react";
import { Loader2, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { tasteAddExamples } from "@/lib/taste-api";
import { useWizard } from "../wizard-ui";

const ACCEPT = ".png,.jpg,.jpeg,.webp,.html,.htm";
const MAX_BYTES = 8_000_000;
type Label = "liked" | "disliked";

const urlList = (text: string) => text.split(/\s+/).map((u) => u.trim()).filter((u) => /^https?:\/\/\S+$/i.test(u)).slice(0, 20);

async function encode(file: File): Promise<string> {
  if (/\.html?$/i.test(file.name)) return file.text();
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** Contrastive examples: websites the user likes and ones they don't, as screenshots or HTML. */
export default function ExampleSites({ onDone }: { onDone: (text: string, jobId: string | null) => void }) {
  const { sessionId, send, adoptModel } = useWizard();
  const [picked, setPicked] = useState<Record<Label, File[]>>({ liked: [], disliked: [] });
  const [urls, setUrls] = useState<Record<Label, string>>({ liked: "", disliked: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const inputs = { liked: useRef<HTMLInputElement>(null), disliked: useRef<HTMLInputElement>(null) };

  const add = (label: Label, list: FileList) => {
    const files = Array.from(list);
    const tooBig = files.filter((f) => f.size > MAX_BYTES);
    setError(tooBig.length ? `${tooBig.map((f) => f.name).join(", ")}: files must be under 8 MB` : "");
    setPicked((p) => ({ ...p, [label]: [...p[label], ...files.filter((f) => f.size <= MAX_BYTES)].slice(0, 20) }));
  };

  async function save() {
    if (!sessionId) return;
    setSaving(true); setError("");
    try {
      const files = await Promise.all((["liked", "disliked"] as const).flatMap((label) => picked[label].map(async (f) => ({ name: f.name, label, content: await encode(f) }))));
      const pages = (["liked", "disliked"] as const).flatMap((label) => urlList(urls[label]).map((url) => ({ name: url, label, url, content: "" })));
      if (pages.length) setStatus(`Opening ${pages.length} page${pages.length === 1 ? "" : "s"} you pasted…`);
      const result = await tasteAddExamples(sessionId, [...files, ...pages]);
      adoptModel?.(result.model_id);
      const text = `Added ${result.added.liked} site${result.added.liked === 1 ? "" : "s"} I like and ${result.added.disliked} I don’t.`;
      onDone(text, result.job_id);
      send(text, "event");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
      setStatus("");
    }
  }

  const count = (label: Label) => picked[label].length + urlList(urls[label]).length;
  const column = (label: Label, title: string, Icon: typeof ThumbsUp) => (
    <div className="min-w-0 flex-1">
      <Button type="button" size="sm" variant="outline" className="w-full justify-start" disabled={saving} onClick={() => inputs[label].current?.click()}>
        <Icon />{title}{count(label) > 0 && <span className="ml-auto font-mono text-[11px] text-muted-foreground">{count(label)}</span>}
      </Button>
      <input ref={inputs[label]} type="file" multiple accept={ACCEPT} hidden aria-label={title} onChange={(e) => { if (e.target.files?.length) add(label, e.target.files); e.target.value = ""; }} />
      <textarea
        aria-label={`${title}: paste URLs`}
        rows={2}
        value={urls[label]}
        disabled={saving}
        onChange={(e) => setUrls((u) => ({ ...u, [label]: e.target.value }))}
        placeholder="…or paste URLs, one per line"
        className="mt-1.5 w-full resize-y rounded border border-border bg-background px-2 py-1 text-[11.5px] leading-5 outline-none focus:border-foreground/40"
      />
      {picked[label].length > 0 && (
        <ul className="m-0 mt-1.5 list-none space-y-0.5 p-0">
          {picked[label].map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center gap-1 text-[11.5px] text-muted-foreground">
              <span className="min-w-0 flex-1 truncate">{f.name}</span>
              <button type="button" aria-label={`Remove ${f.name}`} className="hover:text-foreground" onClick={() => setPicked((p) => ({ ...p, [label]: p[label].filter((_, j) => j !== i) }))}><X className="size-3" /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  const total = count("liked") + count("disliked");
  // The grader needs both kinds and at least four examples in all.
  const enough = count("liked") >= 2 && count("disliked") >= 2;
  return (
    <div>
      <div className="flex gap-2">
        {column("liked", "Sites I like", ThumbsUp)}
        {column("disliked", "Sites I don’t like", ThumbsDown)}
      </div>
      {total > 0 && (
        <div className="mt-2 flex items-center gap-2">
          <span className="flex-1 text-[11.5px] text-muted-foreground">{status || (enough ? "" : "Add at least two of each.")}</span>
          <Button type="button" size="sm" disabled={saving || !enough} onClick={() => void save()}>
            {saving && <Loader2 className="animate-spin" />}Use these {total} examples
          </Button>
        </div>
      )}
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
    </div>
  );
}
