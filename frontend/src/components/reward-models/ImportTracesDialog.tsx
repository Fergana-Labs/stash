"use client";

import { useEffect, useRef, useState } from "react";
import { FileUp, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { rmImportTraces, rmListFormats } from "@/lib/api";
import type { RmFormat, RmImportResult } from "@/lib/types";
import { Field } from "./rm-ui";
import { errorMessage } from "./rm-text";

export default function ImportTracesDialog({ onImported }: { onImported: () => void }) {
  const [open, setOpen] = useState(false);
  const [formats, setFormats] = useState<RmFormat[] | null>(null);
  const [format, setFormat] = useState("auto");
  const [data, setData] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<RmImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open || formats) return;
    rmListFormats()
      .then(setFormats)
      .catch((e) => toast.error(errorMessage(e)));
  }, [open, formats]);

  function reset() {
    setData("");
    setFileName(null);
    setResult(null);
    setError(null);
  }

  async function readFile(file: File) {
    setData(await file.text());
    setFileName(file.name);
    setResult(null);
    setError(null);
  }

  async function submit() {
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      const imported = await rmImportTraces(format, data);
      setResult(imported);
      onImported();
    } catch (e) {
      // The server's 422 names the formats it tried; show it verbatim.
      setError(errorMessage(e));
    } finally {
      setImporting(false);
    }
  }

  const selected = formats?.find((f) => f.name === format);
  const formatOptions = [
    { value: "auto", label: "Auto-detect" },
    ...(formats ?? []).map((f) => ({ value: f.name, label: f.name })),
  ];

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Upload />
          Import a file
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import traces</DialogTitle>
          <DialogDescription>
            Paste or upload agent traces. OpenAI, Anthropic, OpenTelemetry, Langfuse, LangSmith, Claude Code,
            Codex, and Stash Trace Format are supported.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-[200px_1fr] items-start gap-4">
          <Field label="Format">
            <Select
              value={format}
              onChange={setFormat}
              options={formatOptions}
              disabled={formats === null}
              aria-label="Trace format"
              className="h-8 w-full px-2.5 text-[13px]"
            />
          </Field>
          <p className="m-0 mt-6 text-[12px] leading-snug text-muted-foreground">
            {format === "auto"
              ? "The format is detected from the payload's shape."
              : selected?.description}
          </p>
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[12px] font-medium text-dim">Data</span>
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              className="inline-flex cursor-pointer items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
            >
              <FileUp className="h-3.5 w-3.5" />
              {fileName ?? "Choose file…"}
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".jsonl,.json,.ndjson,.txt"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void readFile(file);
                e.target.value = "";
              }}
            />
          </div>
          <Textarea
            value={data}
            onChange={(e) => {
              setData(e.target.value);
              setFileName(null);
            }}
            placeholder={'{"title": "Refund request", "steps": [{"role": "user", "content": "…"}]}'}
            spellCheck={false}
            className="field-sizing-fixed h-56 resize-none font-mono text-[12px] leading-relaxed md:text-[12px]"
          />
        </div>

        {result && (
          <div className="rounded-md border border-green-600/25 bg-green-600/8 px-3 py-2 text-[12.5px] text-green-700 dark:text-green-400">
            Imported {result.imported} trace{result.imported === 1 ? "" : "s"} as <span className="font-mono">{result.format}</span>
          </div>
        )}
        {error && (
          <pre className="m-0 max-h-40 overflow-auto rounded-md border border-red-500/25 bg-red-500/8 px-3 py-2 font-mono text-[12px] whitespace-pre-wrap text-red-600">
            {error}
          </pre>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {result ? "Done" : "Cancel"}
          </Button>
          <Button onClick={() => void submit()} disabled={importing || data.trim() === ""}>
            {importing && <Loader2 className="animate-spin" />}
            {importing ? "Importing…" : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
