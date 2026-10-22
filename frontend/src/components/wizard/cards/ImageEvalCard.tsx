"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Images } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { ConnectAgent, STAGES, UploadBox } from "@/components/image-eval/ImageEvalDetail";
import { imageEvalGet, imageEvalUploadExamples, type ImageEvalDetail, type ImageEvalLabel } from "@/lib/image-eval-api";
import { CardShell, pct, useWizard } from "../wizard-ui";

const UPLOAD_BATCH = 10;
const PARALLEL_UPLOADS = 3;
const MIN_LIKED = 3;
const POLL_MS = 3000;

/** Image style evals in the wizard: upload examples, follow the build, connect an agent. */
export default function ImageEvalCard({ section, evalId, readOnly = false }: { section?: string; evalId: string; readOnly?: boolean }) {
  const [data, setData] = useState<ImageEvalDetail | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setData(await imageEvalGet(evalId)); setError(""); } catch (e) { setError(errorMessage(e)); }
  }, [evalId]);
  useEffect(() => {
    void load();
    if (section !== "progress") return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [load, section]);
  const alert = error && <p role="alert" className="text-sm text-destructive">{error}</p>;
  if (!data) return <CardShell icon={Images} title="Your eval">{alert || <p role="status" className="text-sm text-muted-foreground">Loading…</p>}</CardShell>;
  if (section === "examples") return <Examples data={data} reload={load} readOnly={readOnly} error={alert} />;
  if (section === "progress") return <Progress data={data} readOnly={readOnly} error={alert} />;
  return <Connect data={data} error={alert} />;
}

type Pending = { key: string; url: string; label: ImageEvalLabel; state: "uploading" | "done" | "error" };

function Examples({ data, reload, readOnly, error }: { data: ImageEvalDetail; reload: () => Promise<void>; readOnly: boolean; error: React.ReactNode }) {
  const { send } = useWizard();
  const [pending, setPending] = useState<Pending[]>([]);
  const [uploadError, setUploadError] = useState("");
  const [showDisliked, setShowDisliked] = useState(false);
  const [sent, setSent] = useState(false);
  // Thumbnails use object URLs; free them when the card goes away, not while they are shown.
  const urls = useRef<string[]>([]);
  useEffect(() => () => urls.current.forEach((url) => URL.revokeObjectURL(url)), []);
  const uploading = pending.filter((p) => p.state === "uploading").length;
  const { liked, disliked } = data.examples;

  async function upload(label: ImageEvalLabel, files: File[]) {
    setUploadError("");
    const added = files.map((file, i) => ({ key: `${Date.now()}-${i}-${file.name}`, url: URL.createObjectURL(file), label, state: "uploading" as const }));
    urls.current.push(...added.map((a) => a.url));
    setPending((prev) => [...prev, ...added]);
    const batches: number[] = [];
    for (let i = 0; i < files.length; i += UPLOAD_BATCH) batches.push(i);
    const mark = (from: number, state: Pending["state"]) => {
      const keys = new Set(added.slice(from, from + UPLOAD_BATCH).map((a) => a.key));
      setPending((prev) => prev.map((p) => (keys.has(p.key) ? { ...p, state } : p)));
    };
    // A few batches at once: uploads only store the images, so the server answers quickly.
    let next = 0;
    await Promise.all(Array.from({ length: Math.min(PARALLEL_UPLOADS, batches.length) }, async () => {
      while (next < batches.length) {
        const from = batches[next++];
        try {
          await imageEvalUploadExamples(data.id, label, files.slice(from, from + UPLOAD_BATCH));
          mark(from, "done");
        } catch (e) {
          mark(from, "error");
          setUploadError(errorMessage(e));
        }
      }
    }));
    await reload();
  }

  const locked = readOnly || sent;
  const shown = pending.filter((p) => p.label === "liked");
  const total = pending.length;
  return (
    <CardShell icon={Images} title="Show it the style" subtitle="Drop in images in the style you want. That's all it needs.">
      {error}
      {uploadError && <p role="alert" className="text-sm text-destructive">{uploadError}</p>}
      <UploadBox label="liked" title={liked ? `Images in the style (${liked})` : "Images in the style"} disabled={locked} onFiles={(f) => void upload("liked", f)} />
      {total > 0 && (
        <div className="mt-3 space-y-2">
          {uploading > 0 && (
            <div role="progressbar" aria-label="Uploading images" aria-valuemin={0} aria-valuemax={total} aria-valuenow={total - uploading} className="h-1.5 overflow-hidden rounded bg-muted">
              <div className="h-full bg-brand-500 transition-all" style={{ width: `${((total - uploading) / total) * 100}%` }} />
            </div>
          )}
          {shown.length > 0 && (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(56px,1fr))] gap-1.5">
              {shown.map((p) => (
                // eslint-disable-next-line @next/next/no-img-element -- local object URLs of the files being uploaded
                <img key={p.key} src={p.url} alt="" className={`aspect-square w-full rounded object-cover transition-opacity ${p.state === "done" ? "opacity-100" : p.state === "error" ? "opacity-30 ring-2 ring-destructive" : "animate-pulse opacity-40"}`} />
              ))}
            </div>
          )}
        </div>
      )}
      {showDisliked ? (
        <div className="mt-3">
          <UploadBox label="disliked" title={`Images that aren't the style (${disliked})`} disabled={locked} onFiles={(f) => void upload("disliked", f)} />
        </div>
      ) : !readOnly && (
        <button type="button" className="mt-2 text-xs text-muted-foreground underline" onClick={() => setShowDisliked(true)}>
          Also add images that aren&apos;t the style (optional)
        </button>
      )}
      <div className="mt-3 flex items-center justify-between gap-3">
        <p role="status" className="text-xs text-muted-foreground">
          {uploading ? `Uploading ${total - uploading}/${total}…` : liked < MIN_LIKED ? `Add at least ${MIN_LIKED}; 20 or more works much better.` : "Stash draws its own near-misses to learn from, so you don't need to label anything."}
        </p>
        {!readOnly && <Button size="sm" disabled={locked || uploading > 0 || liked < MIN_LIKED} onClick={() => {
          setSent(true);
          send(`I added ${liked} images in the style${disliked ? ` and ${disliked} that aren't` : ""}.`, "event");
        }}>Build it</Button>}
      </div>
    </CardShell>
  );
}

function Progress({ data, readOnly, error }: { data: ImageEvalDetail; readOnly: boolean; error: React.ReactNode }) {
  const { send } = useWizard();
  const notified = useRef(false);
  const stage = data.build?.stage;
  useEffect(() => {
    if (readOnly || notified.current || (stage !== "done" && stage !== "failed")) return;
    const key = `image-eval-build:${data.id}:${stage}:${data.updated_at}`;
    if (sessionStorage.getItem(key)) return;
    notified.current = true;
    sessionStorage.setItem(key, "seen");
    send(stage === "done" ? "The build finished." : "The build failed.", "event");
  }, [data, readOnly, send, stage]);
  const total = data.build?.total ?? 0;
  return (
    <CardShell icon={Images} title={stage === "done" ? "Built" : "Building your eval"}>
      {error}
      <p role="status" className={stage === "failed" ? "text-sm text-destructive" : "text-sm text-muted-foreground"}>
        {stage === "failed" ? data.build?.error || "The build failed." : stage === "done" ? "Done." : `${STAGES[stage ?? "queued"]}${stage === "imitations" && total ? ` ${data.build?.done ?? 0}/${total}` : ""}`}
      </p>
      {stage !== "done" && stage !== "failed" && <p className="mt-1 text-xs text-muted-foreground">This takes a few minutes. You can leave this page and come back.</p>}
    </CardShell>
  );
}

function Connect({ data, error }: { data: ImageEvalDetail; error: React.ReactNode }) {
  return (
    <CardShell icon={Images} title="Your eval is ready"
      subtitle={`${pct(data.heldout_accuracy)} right on examples it did not train on · ${data.examples.liked} liked · ${data.examples.imitations} imitations`}>
      {error}
      <ConnectAgent id={data.id} />
      {data.model_id && <p className="mt-3 text-xs"><Link className="underline" href={`/reward-models/evals/${data.model_id}`}>Open the eval</Link> to watch your agent&apos;s calls and label them.</p>}
    </CardShell>
  );
}
