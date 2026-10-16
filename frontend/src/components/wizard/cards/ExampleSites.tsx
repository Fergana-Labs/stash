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

async function encode(file: File): Promise<string> {
  if (/\.html?$/i.test(file.name)) return file.text();
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** Contrastive examples: websites the user likes and ones they don't, as screenshots or HTML. */
export default function ExampleSites({ onDone }: { onDone: (text: string) => void }) {
  const { sessionId, send, adoptModel } = useWizard();
  const [picked, setPicked] = useState<Record<Label, File[]>>({ liked: [], disliked: [] });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
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
      const result = await tasteAddExamples(sessionId, files);
      adoptModel?.(result.model_id);
      const text = `Added ${result.added.liked} site${result.added.liked === 1 ? "" : "s"} I like and ${result.added.disliked} I don’t.`;
      onDone(text);
      send(text, "event");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const column = (label: Label, title: string, Icon: typeof ThumbsUp) => (
    <div className="min-w-0 flex-1">
      <Button type="button" size="sm" variant="outline" className="w-full justify-start" disabled={saving} onClick={() => inputs[label].current?.click()}>
        <Icon />{title}{picked[label].length > 0 && <span className="ml-auto font-mono text-[11px] text-muted-foreground">{picked[label].length}</span>}
      </Button>
      <input ref={inputs[label]} type="file" multiple accept={ACCEPT} hidden aria-label={title} onChange={(e) => { if (e.target.files?.length) add(label, e.target.files); e.target.value = ""; }} />
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

  const total = picked.liked.length + picked.disliked.length;
  // The grader needs both kinds and at least four examples in all.
  const enough = picked.liked.length >= 2 && picked.disliked.length >= 2;
  return (
    <div className="mt-3 border-t border-border pt-3">
      <p className="m-0 mb-2 text-[12px] text-muted-foreground">Or show it example sites: screenshots or HTML of designs you like, and ones you don’t.</p>
      <div className="flex gap-2">
        {column("liked", "Sites I like", ThumbsUp)}
        {column("disliked", "Sites I don’t like", ThumbsDown)}
      </div>
      {total > 0 && (
        <div className="mt-2 flex items-center gap-2">
          <span className="flex-1 text-[11.5px] text-muted-foreground">{enough ? "" : "Add at least two of each."}</span>
          <Button type="button" size="sm" disabled={saving || !enough} onClick={() => void save()}>
            {saving && <Loader2 className="animate-spin" />}Use these {total} examples
          </Button>
        </div>
      )}
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
    </div>
  );
}
