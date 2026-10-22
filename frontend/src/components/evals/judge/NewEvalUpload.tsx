"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { errorMessage } from "@/components/reward-models/rm-text";
import UploadBox from "./UploadBox";
import { evalBuild, evalCreate, evalUploadExamples } from "@/lib/evals-api";

const BATCH = 10;
const PARALLEL = 3;

/** New eval: drop examples of good work, and it creates the eval, uploads them, starts
 * the build and opens the eval, where the build shows its progress. */
export default function NewEvalUpload() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<{ name: string; url: string | null; done: boolean }[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const urls = useRef<string[]>([]);
  useEffect(() => () => urls.current.forEach((u) => URL.revokeObjectURL(u)), []);

  async function start(picked: File[]) {
    setError("");
    setWorking(true);
    const shown = picked.map((f) => ({ name: f.name, url: f.type.startsWith("image/") ? URL.createObjectURL(f) : null, done: false }));
    urls.current.push(...shown.flatMap((s) => (s.url ? [s.url] : [])));
    setFiles(shown);
    try {
      setStatus("Creating your eval…");
      const created = await evalCreate(name.trim() || "Untitled eval");
      let next = 0;
      let uploaded = 0;
      setStatus(`Uploading 0/${picked.length}…`);
      await Promise.all(Array.from({ length: PARALLEL }, async () => {
        while (next < picked.length) {
          const from = next;
          next += BATCH;
          await evalUploadExamples(created.id, "good", picked.slice(from, from + BATCH));
          uploaded += Math.min(BATCH, picked.length - from);
          setFiles((prev) => prev.map((f, i) => (i >= from && i < from + BATCH ? { ...f, done: true } : f)));
          setStatus(`Uploading ${uploaded}/${picked.length}…`);
        }
      }));
      setStatus("Starting the build…");
      await evalBuild(created.id);
      router.push(`/reward-models/evals/${created.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setWorking(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-3">
      <input value={name} onChange={(e) => setName(e.target.value)} disabled={working} maxLength={160}
        placeholder="Name it (optional), e.g. Yoko's drawing style" aria-label="Eval name"
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm" />
      <UploadBox title="Drop examples of good work" disabled={working} onFiles={(f) => void start(f)} />
      {files.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(52px,1fr))] gap-1.5">
          {files.map((f, i) => f.url
            // eslint-disable-next-line @next/next/no-img-element -- local previews of the files being uploaded
            ? <img key={i} src={f.url} alt="" className={`aspect-square w-full rounded object-cover transition-opacity ${f.done ? "opacity-100" : "animate-pulse opacity-40"}`} />
            : <span key={i} title={f.name} className={`flex aspect-square w-full items-center justify-center truncate rounded border border-border px-1 text-[9px] ${f.done ? "" : "animate-pulse opacity-50"}`}>{f.name}</span>)}
        </div>
      )}
      <p role={error ? "alert" : "status"} className={`text-xs ${error ? "text-destructive" : "text-muted-foreground"}`}>
        {error || status || "Stash learns what good looks like from them and gives your agents an endpoint that scores their work. You can add examples of bad work on the next page."}
      </p>
    </div>
  );
}
