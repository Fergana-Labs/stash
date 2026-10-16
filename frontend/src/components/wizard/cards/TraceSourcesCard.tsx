"use client";

import { useRef, useState } from "react";
import { FileUp, FolderOpen, History, Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { readTraceEntries, type TraceFile } from "@/components/reward-models/trace-files";
import { cn } from "@/lib/utils";
import { CardShell, useWizard } from "../wizard-ui";
import { uploadWebsiteTraces } from "../website-traces";
import ExampleSites from "./ExampleSites";

const asTraceFiles = (list: FileList) =>
  Array.from(list).map((file) => ({ file, path: file.webkitRelativePath || file.name }));

/** First step of a website eval: upload past sessions, or let the wizard search connected history. */
export default function TraceSourcesCard() {
  const { sessionId, send, adoptModel, busy } = useWizard();
  const [status, setStatus] = useState("");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const files = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const working = !!status;

  async function upload(read: () => Promise<TraceFile[]>) {
    if (!sessionId || working) return;
    setError(""); setStatus("Reading your sessions…");
    try {
      const picked = await read();
      const result = await uploadWebsiteTraces(sessionId, picked, setStatus);
      adoptModel?.(result.modelId);
      setDone(`Uploaded ${result.uploaded} session${result.uploaded === 1 ? "" : "s"}${result.skipped ? ` · skipped ${result.skipped} other file${result.skipped === 1 ? "" : "s"}` : ""}.`);
      send(result.event, "event");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setStatus("");
    }
  }

  if (done) {
    return <CardShell icon={Upload} title="Your past sessions"><p role="status" className="m-0 text-[12.5px] text-muted-foreground">{done}</p></CardShell>;
  }

  return (
    <CardShell icon={Upload} title="Add your past sessions" subtitle="Sessions where you built websites with an agent and told it what to change">
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop session files or folders, or click to choose files"
        aria-disabled={working}
        onClick={() => files.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") files.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault(); setDrag(false);
          const entries = Array.from(e.dataTransfer.items).map((item) => item.webkitGetAsEntry()).filter((x): x is FileSystemEntry => !!x);
          void upload(() => readTraceEntries(entries));
        }}
        className={cn("grid cursor-pointer place-items-center gap-1 rounded-md border border-dashed border-border px-4 py-6 text-center transition-colors hover:bg-surface/60", drag && "border-brand-500 bg-brand-500/5", working && "pointer-events-none opacity-60")}
      >
        {working ? <Loader2 className="size-5 animate-spin text-muted-foreground" /> : <FileUp className="size-5 text-muted-foreground" />}
        <p className="m-0 text-[12.5px]">{working ? status : <>Drop session files or a whole folder here, or <span className="underline">browse</span></>}</p>
        <p className="m-0 text-[11px] text-muted-foreground">
          Codex sessions live in <code>~/.codex/sessions</code> · press ⌘⇧. in the file picker to show hidden folders
        </p>
      </div>
      <input ref={files} type="file" multiple accept=".jsonl" hidden onChange={(e) => { const list = e.target.files; if (list?.length) void upload(async () => asTraceFiles(list)); e.target.value = ""; }} />
      {/* webkitdirectory is not in React's input attribute types. */}
      <input ref={folder} type="file" hidden {...{ webkitdirectory: "" }} onChange={(e) => { const list = e.target.files; if (list?.length) void upload(async () => asTraceFiles(list)); e.target.value = ""; }} />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" disabled={working} onClick={() => folder.current?.click()}><FolderOpen />Choose a folder</Button>
        <span className="flex-1" />
        <Button type="button" size="sm" variant="ghost" disabled={working || busy} onClick={() => send("Search my connected history instead of uploading.")}><History />Search my connected history instead</Button>
      </div>
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
      {!working && <ExampleSites onDone={setDone} />}
    </CardShell>
  );
}
