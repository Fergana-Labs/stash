"use client";

import { useEffect, useRef, useState } from "react";
import { FileUp, FolderUp, Loader2, Upload } from "lucide-react";
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
import type { RmFormat } from "@/lib/types";
import { Field } from "./rm-ui";
import { errorMessage } from "./rm-text";
import { importTraceFiles, type FileImportResult, type TraceFile } from "./trace-files";

export default function ImportTracesDialog({ onImported }: { onImported: () => void }) {
  const [open, setOpen] = useState(false);
  const [formats, setFormats] = useState<RmFormat[] | null>(null);
  const [format, setFormat] = useState("auto");
  const [data, setData] = useState("");
  const [files, setFiles] = useState<TraceFile[]>([]);
  const [progress, setProgress] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<FileImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const folderInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open || formats) return;
    rmListFormats()
      .then(setFormats)
      .catch((e) => toast.error(errorMessage(e)));
  }, [open, formats]);

  function reset() {
    setData("");
    setFiles([]);
    setResult(null);
    setError(null);
  }

  function selectFiles(selected: TraceFile[]) {
    setFiles(selected);
    setData("");
    setResult(null);
    setError(null);
  }

  async function submit() {
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      const imported = files.length > 0
        ? await importTraceFiles(files, format, setProgress)
        : { imported: (await rmImportTraces(format, data)).imported, failed: [], skipped: [] };
      setResult(imported);
      // Keep only failures selected, so retrying cannot re-import successful files.
      setFiles(imported.failed.map((failure) => failure.entry));
      setData("");
      if (imported.imported > 0) onImported();
      if (imported.imported === 0 && imported.failed.length === 0) {
        setError("No trace files found. Choose JSON, JSONL, NDJSON, or text trace files.");
      }
    } catch (e) {
      // The server's 422 names the formats it tried; show it verbatim.
      setError(errorMessage(e));
    } finally {
      setImporting(false);
      setProgress(null);
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
        if (importing) return;
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Upload />
          Import traces
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import traces</DialogTitle>
          <DialogDescription>
            Choose files or a folder, or paste agent traces. OpenAI, Anthropic, OpenTelemetry, Langfuse, LangSmith, Claude Code,
            Codex, and Stash Trace Format are supported.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-[200px_1fr] items-start gap-4">
          <Field label="Format">
            <Select
              value={format}
              onChange={setFormat}
              options={formatOptions}
              disabled={formats === null || importing}
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
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="xs" disabled={importing} onClick={() => fileInput.current?.click()}>
                <FileUp />Choose files
              </Button>
              <Button variant="ghost" size="xs" disabled={importing} onClick={() => folderInput.current?.click()}>
                <FolderUp />Choose folder
              </Button>
            </div>
            <input
              ref={fileInput}
              type="file"
              multiple
              aria-label="Trace files"
              accept=".jsonl,.json,.ndjson,.txt"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) selectFiles(Array.from(e.target.files, (file) => ({ file, path: file.name })));
                e.target.value = "";
              }}
            />
            <input
              ref={folderInput}
              type="file"
              multiple
              aria-label="Trace folder"
              {...({ webkitdirectory: "" } as Record<string, string>)}
              className="hidden"
              onChange={(e) => {
                if (!e.target.files?.length) {
                  reset();
                  setError("The selected folder is empty.");
                  return;
                }
                selectFiles(Array.from(e.target.files, (file) => ({ file, path: file.webkitRelativePath })));
                e.target.value = "";
              }}
            />
          </div>
          {files.length > 0 ? (
            <div className="rounded-md border border-border p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[13px]">{files.length} file{files.length === 1 ? "" : "s"} selected</span>
                <Button variant="ghost" size="xs" disabled={importing} onClick={reset}>Clear</Button>
              </div>
              <ul className="m-0 max-h-40 list-none overflow-y-auto p-0 text-[12px] text-muted-foreground">
                {files.map((entry, index) => <li key={index} className="break-all py-0.5">{entry.path}</li>)}
              </ul>
              <p className="m-0 mt-2 text-[12px] text-muted-foreground">Includes nested folders. Manifests, hidden files, and other supporting files are skipped.</p>
            </div>
          ) : result !== null && result.imported > 0 ? null : <Textarea
            aria-label="Trace data"
            disabled={importing}
            value={data}
            onChange={(e) => {
              setData(e.target.value);
              setResult(null);
              setError(null);
            }}
            placeholder={'{"title": "Refund request", "steps": [{"role": "user", "content": "…"}]}'}
            spellCheck={false}
            className="field-sizing-fixed h-56 resize-none font-mono text-[12px] leading-relaxed md:text-[12px]"
          />}
        </div>

        {progress && <p role="status" className="m-0 truncate text-[12px] text-muted-foreground">Importing {progress}…</p>}
        {result && result.imported > 0 && (
          <p role="status" className="m-0 text-[13px]">Imported {result.imported} trace{result.imported === 1 ? "" : "s"}.</p>
        )}
        {result && result.skipped.length > 0 && <p className="m-0 max-h-24 overflow-auto break-words text-[12px] text-muted-foreground">Skipped supporting files: {result.skipped.join(", ")}</p>}
        {result && result.failed.length > 0 && <pre role="alert" className="m-0 max-h-40 overflow-auto text-[12px] whitespace-pre-wrap text-red-600">{result.failed.map((failure) => failure.message).join("\n")}</pre>}
        {error && (
          <pre className="m-0 max-h-40 overflow-auto rounded-md border border-red-500/25 bg-red-500/8 px-3 py-2 font-mono text-[12px] whitespace-pre-wrap text-red-600">
            {error}
          </pre>
        )}

        <DialogFooter>
          <Button variant="outline" disabled={importing} onClick={() => { setOpen(false); reset(); }}>
            {result ? "Done" : "Cancel"}
          </Button>
          <Button onClick={() => void submit()} disabled={importing || (files.length === 0 && data.trim() === "")}>
            {importing && <Loader2 className="animate-spin" />}
            {importing ? "Importing…" : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
