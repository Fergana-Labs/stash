"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Images } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { ConnectAgent, STAGES, UploadBox } from "@/components/image-eval/ImageEvalDetail";
import { imageEvalGet, imageEvalUploadExamples, type ImageEvalDetail, type ImageEvalLabel } from "@/lib/image-eval-api";
import { CardShell, pct, useWizard } from "../wizard-ui";

const UPLOAD_BATCH = 20;
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

function Examples({ data, reload, readOnly, error }: { data: ImageEvalDetail; reload: () => Promise<void>; readOnly: boolean; error: React.ReactNode }) {
  const { send } = useWizard();
  const [busy, setBusy] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [sent, setSent] = useState(false);
  const { liked, disliked } = data.examples;
  async function upload(label: ImageEvalLabel, files: File[]) {
    setUploadError("");
    try {
      for (let i = 0; i < files.length; i += UPLOAD_BATCH) {
        setBusy(`Uploading ${Math.min(i + UPLOAD_BATCH, files.length)}/${files.length}…`);
        await imageEvalUploadExamples(data.id, label, files.slice(i, i + UPLOAD_BATCH));
      }
    } catch (e) { setUploadError(errorMessage(e)); }
    setBusy("");
    await reload();
  }
  const locked = readOnly || sent || !!busy;
  return (
    <CardShell icon={Images} title="Show it the style" subtitle="Images you like teach it the style; images you don't are optional">
      {error}
      {uploadError && <p role="alert" className="text-sm text-destructive">{uploadError}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        <UploadBox label="liked" title={`Images you like (${liked})`} disabled={locked} onFiles={(f) => void upload("liked", f)} />
        <UploadBox label="disliked" title={`Images you don't (${disliked})`} disabled={locked} onFiles={(f) => void upload("disliked", f)} />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <p role="status" className="text-xs text-muted-foreground">
          {busy || (liked < MIN_LIKED ? `Add at least ${MIN_LIKED} images you like; 20 or more works much better.` : "Stash will draw its own close imitations, so you don't need to label anything else.")}
        </p>
        {!readOnly && <Button size="sm" disabled={locked || liked < MIN_LIKED} onClick={() => {
          setSent(true);
          send(`I added ${liked} images I like and ${disliked} I don't.`, "event");
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
