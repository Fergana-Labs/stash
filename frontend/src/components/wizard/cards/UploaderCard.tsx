"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileUp, ImageIcon, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { evalReadFile, imAddExamples, imGet, type Item, type NewExample, type OutputType } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";

const ACCEPT = ".txt,.md,.json,.jsonl,.ndjson,.csv,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp,.gif";
const MAX_BYTES = 2 * 1024 * 1024;

/** Pasted text -> examples. JSONL ({item|text, label}), CSV with a label column, `---` blocks, or one per line. */
export function parsePasted(text: string, labels: string[]): NewExample[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const lines = trimmed.split("\n").map((l) => l.trim()).filter(Boolean);
  const label = (value: unknown) => (typeof value === "string" && labels.includes(value) ? value : null);
  const toExample = (item: Item, l: string | null): NewExample => ({ item, label: l, needs_review: l === null });
  if (lines.every((l) => l.startsWith("{"))) {
    try {
      return lines.map((l) => {
        const row = JSON.parse(l) as Record<string, unknown>;
        const { label: rowLabel, ...rest } = row;
        const item = (row.item ?? row.text ?? row.input ?? rest) as Item;
        return toExample(item, label(rowLabel));
      });
    } catch { /* not JSONL; fall through */ }
  }
  const header = lines[0].toLowerCase().split(",").map((h) => h.trim());
  const labelCol = header.indexOf("label");
  if (labelCol >= 0 && header.length > 1 && lines.length > 1) {
    return lines.slice(1).map((l) => {
      const cells = l.split(",");
      const body = cells.filter((_, i) => i !== labelCol).join(",").trim();
      return toExample(body.replace(/^"|"$/g, ""), label(cells[labelCol]?.trim()));
    });
  }
  if (/\n-{3,}\n/.test(trimmed)) return trimmed.split(/\n-{3,}\n/).map((b) => toExample(b.trim(), null)).filter((e) => e.item);
  return lines.map((l) => toExample(l, null));
}

export default function UploaderCard({ prompt }: { prompt?: string }) {
  const { modelId, send, refresh } = useWizard();
  const [labels, setLabels] = useState<string[]>([]);
  const [outputType, setOutputType] = useState<OutputType>("choice");
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [labelAll, setLabelAll] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!modelId) return;
    imGet(modelId).then((d) => {
      const v = d.draft ?? d.active;
      setOutputType(d.model.output_type);
      setLabels(d.model.output_type === "preference" ? ["good", "bad"] : [...(v?.labels ?? []).map((l) => l.id), ...(d.model.output_type === "multi" ? ["none"] : [])]);
    }).catch((e) => setError(errorMessage(e)));
  }, [modelId]);

  const addFiles = useCallback((list: FileList | File[]) => {
    const picked = Array.from(list);
    const tooBig = picked.filter((f) => f.size > MAX_BYTES);
    setError(tooBig.length ? `${tooBig.map((f) => f.name).join(", ")}: files must be under 2 MB` : "");
    setFiles((prev) => [...prev, ...picked.filter((f) => f.size <= MAX_BYTES)].slice(0, 50));
  }, []);

  if (!modelId) return <CardShell icon={Upload} title="Add examples"><NeedsModel /></CardShell>;
  const pasted = parsePasted(text, labels);

  async function submit() {
    if (!modelId) return;
    setBusy(true); setError("");
    try {
      const chosen = labelAll || null;
      const fromFiles: NewExample[] = [];
      for (const [i, file] of files.entries()) {
        setStatus(`Reading ${file.name} (${i + 1}/${files.length})${file.type.startsWith("image/") ? " — describing the image" : ""}…`);
        const item = await evalReadFile(file);
        fromFiles.push({ item, label: chosen, needs_review: chosen === null });
      }
      const rows = [...fromFiles, ...pasted.map((e) => (chosen && !e.label ? { ...e, label: chosen, needs_review: false } : e))];
      if (!rows.length) return;
      setStatus("Saving…");
      await imAddExamples(modelId, rows);
      const images = files.filter((f) => f.type.startsWith("image/")).length;
      const unlabeled = rows.filter((r) => !r.label).length;
      setFiles([]); setText(""); setStatus(""); refresh();
      send(`Added ${rows.length} example${rows.length === 1 ? "" : "s"}${images ? ` (${images} image${images === 1 ? "" : "s"})` : ""}; ${unlabeled ? `${unlabeled} need labels` : "all labeled"}.`, "event");
    } catch (e) {
      setError(errorMessage(e)); setStatus("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <CardShell icon={Upload} title="Add examples" subtitle={prompt || "Files, images, or pasted text — labels optional"}>
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop files or click to choose"
        onClick={() => input.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
        className={cn("grid cursor-pointer place-items-center gap-1 rounded-md border border-border px-4 py-5 text-center transition-colors hover:bg-surface/60", drag && "border-brand-500 bg-brand-500/5")}
      >
        <FileUp className="size-5 text-muted-foreground" />
        <p className="m-0 text-[12.5px]">Drop files here or <span className="underline">browse</span></p>
        <p className="m-0 text-[11px] text-muted-foreground">Images, PDFs, slides, docs, text, CSV/JSONL · up to 2 MB each</p>
        <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
      </div>
      {files.length > 0 && (
        <ul className="m-0 mt-2 flex list-none flex-wrap gap-1.5 p-0">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px]">
              {f.type.startsWith("image/") && <ImageIcon className="size-3" />}{f.name}
              <button type="button" aria-label={`Remove ${f.name}`} className="text-muted-foreground hover:text-foreground" onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}>×</button>
            </li>
          ))}
        </ul>
      )}
      <textarea
        aria-label="Paste examples"
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`…or paste examples: one per line, blocks separated by ---, JSONL ({"text": …, "label": "${labels[0] ?? "label"}"}), or CSV with a label column`}
        className="mt-2 w-full resize-y rounded-md border border-border bg-background px-2.5 py-2 text-[12px] leading-5 outline-none focus:border-foreground/40"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          Label all as
          <select aria-label="Label all as" value={labelAll} onChange={(e) => setLabelAll(e.target.value)} className="h-7 rounded border border-border bg-background px-1.5 text-[12px] text-foreground">
            <option value="">— label later —</option>
            {labels.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        <span className="flex-1 text-[11.5px] text-muted-foreground">
          {files.length + pasted.length ? `${files.length + pasted.length} ready${pasted.some((p) => p.label) ? ` · ${pasted.filter((p) => p.label).length} with labels` : ""}` : ""}
          {outputType === "preference" && " · labels are good / bad"}
        </span>
        <Button size="sm" disabled={busy || !(files.length + pasted.length)} onClick={() => void submit()}>{busy ? "Adding…" : "Add examples"}</Button>
      </div>
      {status && <p role="status" className="m-0 mt-2 text-[11.5px] text-muted-foreground">{status}</p>}
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
    </CardShell>
  );
}
