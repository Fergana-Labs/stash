"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, Images, Loader2, MessageCircleQuestion } from "lucide-react";
import Markdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { ConnectAgent, UploadBox } from "@/components/image-eval/ImageEvalDetail";
import ImageEvalImage from "@/components/image-eval/ImageEvalImage";
import { imageEvalExampleImagePath, imageEvalExamples, imageEvalGet, imageEvalUploadExamples, type ImageEvalDetail, type ImageEvalExample, type ImageEvalInterview, type ImageEvalLabel, imageEvalAnswer, imageEvalInterview } from "@/lib/image-eval-api";
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
  if (section === "questions") return <Questions data={data} readOnly={readOnly} error={alert} />;
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
        }}>Continue</Button>}
      </div>
    </CardShell>
  );
}

function Questions({ data, readOnly, error }: { data: ImageEvalDetail; readOnly: boolean; error: React.ReactNode }) {
  const { send } = useWizard();
  const [interview, setInterview] = useState<ImageEvalInterview | null>(data.interview?.questions ? data.interview : null);
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [written, setWritten] = useState<Record<number, string>>({});
  const [leaveOut, setLeaveOut] = useState<Set<string>>(new Set());
  const [askError, setAskError] = useState("");
  const [saving, setSaving] = useState(false);
  const done = !!data.interview?.done;
  useEffect(() => {
    if (interview || done) return;
    let live = true;
    imageEvalInterview(data.id).then((i) => { if (live) setInterview(i); }).catch((e) => { if (live) setAskError(errorMessage(e)); });
    return () => { live = false; };
  }, [data.id, interview, done]);

  if (done) {
    const answers = data.interview?.answers ?? [];
    return (
      <CardShell icon={MessageCircleQuestion} title={answers.length ? "What you told it" : "Questions skipped"}>
        {answers.length ? <ul className="space-y-2 text-sm">{answers.map((a, i) => <li key={i}><span className="text-muted-foreground">{a.question}</span><br />{a.answer}</li>)}</ul>
          : <p className="text-sm text-muted-foreground">It will learn from the images alone.</p>}
        {!!data.interview?.left_out.length && <p className="mt-2 text-xs text-muted-foreground">Left out {data.interview.left_out.length} image{data.interview.left_out.length === 1 ? "" : "s"}.</p>}
      </CardShell>
    );
  }
  if (!interview) {
    return (
      <CardShell icon={MessageCircleQuestion} title="Looking through your images" subtitle="Working out the few things only you can tell it">
        {error}
        {askError ? <p role="alert" className="text-sm text-destructive">{askError}</p>
          : <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />This takes about 20 seconds.</p>}
      </CardShell>
    );
  }
  const answerOf = (i: number) => (written[i]?.trim() || picked[i] || "").trim();
  const answered = interview.questions.filter((_, i) => answerOf(i)).length;
  async function submit(skipped: boolean) {
    setSaving(true);
    try {
      const answers = skipped ? [] : interview!.questions.map((q, i) => ({ question: q.question, answer: answerOf(i) })).filter((a) => a.answer);
      await imageEvalAnswer(data.id, { answers, leave_out: skipped ? [] : [...leaveOut], skipped });
      const out = skipped ? 0 : leaveOut.size;
      send(skipped ? "I skipped the questions." : `I answered ${answers.length} question${answers.length === 1 ? "" : "s"}${out ? ` and left out ${out} image${out === 1 ? "" : "s"}` : ""}.`, "event");
    } catch (e) { setAskError(errorMessage(e)); setSaving(false); }
  }
  return (
    <CardShell icon={MessageCircleQuestion} title="A few questions only you can answer" subtitle="Your answers become the rules it judges by">
      {error}
      {askError && <p role="alert" className="text-sm text-destructive">{askError}</p>}
      <ol className="space-y-5">
        {interview.questions.map((q, i) => (
          <li key={i}>
            <p className="text-sm font-medium">{q.question}</p>
            {q.why && <p className="text-xs text-muted-foreground">{q.why}</p>}
            <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label={q.question}>
              {q.options.map((o) => (
                <button key={o} type="button" role="radio" aria-checked={picked[i] === o} disabled={readOnly || saving}
                  onClick={() => setPicked((prev) => ({ ...prev, [i]: prev[i] === o ? "" : o }))}
                  className={`rounded-full border px-3 py-1 text-xs transition-colors ${picked[i] === o ? "border-brand-500 bg-brand-500/10 text-brand-600" : "border-border hover:bg-surface"}`}>
                  {o}
                </button>
              ))}
            </div>
            <input type="text" value={written[i] ?? ""} disabled={readOnly || saving} maxLength={1000}
              onChange={(e) => setWritten((prev) => ({ ...prev, [i]: e.target.value }))}
              placeholder="Or say it in your own words" aria-label={`Your answer: ${q.question}`}
              className="mt-2 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs" />
          </li>
        ))}
        {interview.outliers.length > 0 && (
          <li>
            <p className="text-sm font-medium">{interview.outliers.length === 1 ? "This one" : "These"} didn&apos;t look like the rest. Part of the style?</p>
            <p className="text-xs text-muted-foreground">Tap any that aren&apos;t, and it will leave them out.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {interview.outliers.map((id) => (
                <button key={id} type="button" disabled={readOnly || saving} aria-pressed={leaveOut.has(id)} aria-label={leaveOut.has(id) ? "Leaving out; tap to keep" : "Keep; tap to leave out"}
                  onClick={() => setLeaveOut((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; })}
                  className={`relative w-24 rounded-md border-2 ${leaveOut.has(id) ? "border-destructive opacity-50" : "border-transparent"}`}>
                  <ImageEvalImage path={imageEvalExampleImagePath(data.id, id)} alt="An image that looks unlike the rest" className="h-24 w-24" />
                  <span className="mt-1 block text-[11px]">{leaveOut.has(id) ? "Leave out" : "Keep"}</span>
                </button>
              ))}
            </div>
          </li>
        )}
      </ol>
      {!readOnly && (
        <div className="mt-5 flex items-center justify-between gap-3">
          <button type="button" className="text-xs text-muted-foreground underline" disabled={saving} onClick={() => void submit(true)}>Skip and build from the images alone</button>
          <Button size="sm" disabled={saving || (answered === 0 && leaveOut.size === 0)} onClick={() => void submit(false)}>{saving ? "Saving…" : "Build it"}</Button>
        </div>
      )}
    </CardShell>
  );
}

const STEPS = [
  { stage: "brief", title: "Studying the style", detail: "Reading your images and your answers, and writing down what makes them this style" },
  { stage: "imitations", title: "Drawing near-misses", detail: "Imitating the style, so it learns the real thing from close-but-not-quite" },
  { stage: "training", title: "Training", detail: "Learning to tell your images from the imitations" },
] as const;
const ORDER = ["queued", "brief", "imitations", "training", "done"];

function Progress({ data, readOnly, error }: { data: ImageEvalDetail; readOnly: boolean; error: React.ReactNode }) {
  const { send } = useWizard();
  const notified = useRef(false);
  const stage = data.build?.stage ?? "queued";
  const [imitations, setImitations] = useState<ImageEvalExample[]>([]);
  const elapsed = useElapsed(data.build?.started_at, stage === "done" || stage === "failed");
  useEffect(() => {
    if (stage !== "imitations" && stage !== "training" && stage !== "done") return;
    void imageEvalExamples(data.id).then((all) => setImitations(all.filter((e) => e.source === "imitation"))).catch(() => {});
  }, [data.id, data.build?.done, stage]);
  useEffect(() => {
    if (readOnly || notified.current || (stage !== "done" && stage !== "failed")) return;
    const key = `image-eval-build:${data.id}:${stage}:${data.updated_at}`;
    if (sessionStorage.getItem(key)) return;
    notified.current = true;
    sessionStorage.setItem(key, "seen");
    send(stage === "done" ? "The build finished." : "The build failed.", "event");
  }, [data, readOnly, send, stage]);

  const total = data.build?.total || 12;
  const drawn = data.build?.done ?? 0;
  // Rough weights from real builds: the brief ~1 min, imitations ~3 min, training seconds.
  const fraction = stage === "done" ? 1 : stage === "brief" ? 0.08 : stage === "imitations" ? 0.15 + 0.75 * (drawn / total) : stage === "training" ? 0.93 : 0.02;
  const at = ORDER.indexOf(stage);
  return (
    <CardShell icon={Images} title={stage === "done" ? "Built" : stage === "failed" ? "The build failed" : "Building your eval"}
      subtitle={stage === "done" || stage === "failed" ? undefined : `${elapsed} · usually 4–5 minutes · you can leave and come back`}>
      {error}
      {stage === "failed" ? (
        <p role="alert" className="text-sm text-destructive">{data.build?.error || "Something went wrong."}</p>
      ) : (
        <>
          <div role="progressbar" aria-label="Build progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(fraction * 100)} className="mb-4 h-1.5 overflow-hidden rounded bg-muted">
            <div className="h-full bg-brand-500 transition-all duration-700" style={{ width: `${Math.max(fraction * 100, 3)}%` }} />
          </div>
          <ol className="space-y-3">
            {STEPS.map((step) => {
              const i = ORDER.indexOf(step.stage);
              const state = at > i ? "done" : at === i ? "active" : "waiting";
              return (
                <li key={step.stage} className="flex gap-3">
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center">
                    {state === "done" ? <Check className="size-4 text-emerald-600" aria-label="done" /> : state === "active" ? <Loader2 className="size-4 animate-spin text-brand-500" aria-label="in progress" /> : <span className="size-2 rounded-full bg-muted-foreground/30" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className={state === "waiting" ? "text-sm text-muted-foreground" : "text-sm font-medium"}>
                      {step.title}{step.stage === "imitations" && state !== "waiting" ? ` · ${Math.min(drawn, total)}/${total}` : ""}
                    </p>
                    {state === "active" && <p className="text-xs text-muted-foreground">{step.detail}</p>}
                    {step.stage === "brief" && data.style_brief && (
                      <details className="mt-1 text-xs text-muted-foreground" open={state === "done" && stage === "imitations"}>
                        <summary className="cursor-pointer">What it noticed</summary>
                        <div className="mt-1 [&_li]:mb-1 [&_strong]:text-foreground [&_ul]:list-disc [&_ul]:pl-5"><Markdown>{data.style_brief}</Markdown></div>
                      </details>
                    )}
                    {step.stage === "imitations" && imitations.length > 0 && (
                      <div className="mt-2 grid grid-cols-[repeat(auto-fill,minmax(64px,1fr))] gap-1.5">
                        {imitations.map((e) => <ImageEvalImage key={e.id} path={imageEvalExampleImagePath(data.id, e.id)} alt={`Near-miss: ${e.filename}`} className="aspect-square w-full" />)}
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </CardShell>
  );
}

function useElapsed(startedAt: number | undefined, stopped: boolean) {
  const [now, setNow] = useState(() => Date.now());
  const [mounted] = useState(() => Date.now());
  useEffect(() => {
    if (stopped) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [stopped]);
  const seconds = Math.max(0, Math.floor((now - (startedAt ? startedAt * 1000 : mounted)) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
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
