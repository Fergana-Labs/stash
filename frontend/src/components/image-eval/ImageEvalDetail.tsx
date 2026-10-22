"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { EmptyState, RmPage } from "@/components/reward-models/rm-ui";
import { relativeTime } from "@/components/reward-models/rm-text";
import ImageEvalImage from "@/components/image-eval/ImageEvalImage";
import { cn } from "@/lib/utils";
import Markdown from "react-markdown";
import {
  imageEvalCallImagePath, imageEvalCalls, imageEvalDeleteExample, imageEvalExampleImagePath, imageEvalExamples, imageEvalGet,
  imageEvalBuild, imageEvalLabelCall, imageEvalTrain, imageEvalUploadExamples,
  type ImageEvalBuild, type ImageEvalCall, type ImageEvalDetail as Detail, type ImageEvalExample, type ImageEvalLabel,
} from "@/lib/image-eval-api";

const UPLOAD_BATCH = 20;
const POLL_MS = 5000;

export default function ImageEvalDetail({ id }: { id: string }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [examples, setExamples] = useState<ImageEvalExample[]>([]);
  const [calls, setCalls] = useState<ImageEvalCall[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useBreadcrumbs([{ label: "Evals", href: "/reward-models/evals" }, { label: detail?.name ?? "…" }], `evals-${id}`);

  const load = useCallback(async () => {
    try {
      const [d, e, c] = await Promise.all([imageEvalGet(id), imageEvalExamples(id), imageEvalCalls(id)]);
      setDetail(d); setExamples(e); setCalls(c); setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), POLL_MS);  // agents call while you watch
    return () => clearInterval(timer);
  }, [load]);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    try { await action(); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  async function upload(label: ImageEvalLabel, files: File[]) {
    for (let i = 0; i < files.length; i += UPLOAD_BATCH) {
      setBusy(`Uploading ${Math.min(i + UPLOAD_BATCH, files.length)}/${files.length} ${label}…`);
      await imageEvalUploadExamples(id, label, files.slice(i, i + UPLOAD_BATCH));
    }
  }

  if (!detail) return <RmPage title="Evals">{error ? <p className="text-[13px] text-red-600" role="alert">{error}</p> : <p className="text-[13px] text-muted-foreground">Loading…</p>}</RmPage>;
  const canTrain = detail.examples.liked >= 3 && detail.examples.disliked + detail.examples.imitations >= 3;
  const building = !!detail.build && !["done", "failed"].includes(detail.build.stage);
  return <RmPage title={detail.name} wide description="Examples teach the classifier what you like. Agents score their work against it; label what they send to keep teaching it."
    actions={<>
      {detail.trained && <Button size="sm" variant="outline" disabled={!canTrain || !!busy || building || !detail.needs_training} onClick={() => void run("Training…", () => imageEvalTrain(id))}>
        {detail.needs_training ? "Retrain" : "Up to date"}
      </Button>}
      <Button size="sm" disabled={detail.examples.liked < 3 || !!busy || building} onClick={() => void run("Starting build…", () => imageEvalBuild(id))}>
        {detail.examples.imitations ? "Rebuild" : "Build"}
      </Button>
    </>}>
    {error && <p className="mb-4 text-[13px] text-red-600" role="alert">{error}</p>}
    {busy && <p className="mb-4 text-[13px] text-muted-foreground" role="status">{busy}</p>}
    {detail.build && <BuildStatus build={detail.build} />}
    <Accuracy detail={detail} />
    {detail.style_brief && <StyleBrief brief={detail.style_brief} />}
    <section className="mt-6 grid gap-4 md:grid-cols-2">
      <UploadBox label="liked" title="Examples you like" disabled={!!busy} onFiles={(f) => void run("Uploading…", () => upload("liked", f))} />
      <UploadBox label="disliked" title="Examples you don't like" disabled={!!busy} onFiles={(f) => void run("Uploading…", () => upload("disliked", f))} />
    </section>
    {detail.trained && <ConnectAgent id={id} />}
    <Calls id={id} calls={calls} onLabel={(callId, label, note) => void run("Saving label…", () => imageEvalLabelCall(id, callId, label, note))} />
    <Examples id={id} examples={examples} onDelete={(exampleId) => void run("Removing…", () => imageEvalDeleteExample(id, exampleId))} />
  </RmPage>;
}

export const STAGES: Record<ImageEvalBuild["stage"], string> = {
  queued: "Waiting to start…",
  brief: "Studying your examples and writing a style brief…",
  imitations: "Drawing imitations to learn real from close-but-not-quite…",
  training: "Training…",
  done: "",
  failed: "Build failed",
};

function BuildStatus({ build }: { build: ImageEvalBuild }) {
  if (build.stage === "done") return null;
  return <div role="status" className={cn("mb-4 rounded-md border px-4 py-3 text-[13px]", build.stage === "failed" ? "border-red-300 text-red-700" : "border-border")}>
    {STAGES[build.stage]}{build.stage === "imitations" && build.total ? ` ${build.done ?? 0}/${build.total}` : ""}
    {build.stage === "failed" && build.error && <span className="block text-[12px]">{build.error}</span>}
  </div>;
}

function StyleBrief({ brief }: { brief: string }) {
  return <details className="mt-4 rounded-md border border-border px-4 py-3" open>
    <summary className="cursor-pointer text-[13px] font-semibold">What Stash learned about this style</summary>
    <div className="mt-2 text-[13px] text-muted-foreground [&_li]:mb-1 [&_strong]:text-foreground [&_ul]:list-disc [&_ul]:pl-5"><Markdown>{brief}</Markdown></div>
  </details>;
}

function Accuracy({ detail }: { detail: Detail }) {
  const { liked, disliked } = detail.examples;
  if (!detail.trained) {
    return <EmptyState title={liked >= 3 ? "Ready to build" : "Add examples"}>
      {liked >= 3 ? "Build it: Stash writes a style brief, draws imitations of your liked examples so it learns real from close-but-not-quite, then trains. About 5–10 minutes." : `Upload at least 3 images you like (you have ${liked}), and ideally some you don't. 20 or more liked works much better.`}
    </EmptyState>;
  }
  return <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 rounded-md border border-border px-4 py-3">
    <Quality detail={detail} />
    <div className="text-[13px] text-muted-foreground">{liked} liked · {disliked} disliked{detail.examples.imitations ? ` · ${detail.examples.imitations} imitations` : ""} · {detail.calls} agent calls{detail.trained_at && ` · trained ${relativeTime(detail.trained_at)}`}</div>
    {detail.needs_training && <div className="text-[13px] text-amber-600">New examples since the last training run</div>}
  </div>;
}

export function UploadBox({ label, title, disabled, onFiles }: { label: ImageEvalLabel; title: string; disabled: boolean; onFiles: (files: File[]) => void }) {
  const [over, setOver] = useState(false);
  const pick = (list: FileList | null) => { const files = Array.from(list ?? []).filter((f) => f.type.startsWith("image/") || /\.heic$/i.test(f.name)); if (files.length) onFiles(files); };
  return <label onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
    onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) pick(e.dataTransfer.files); }}
    className={cn("flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed px-4 py-8 text-center", over ? "border-brand-500 bg-brand-500/5" : "border-border", disabled && "cursor-not-allowed opacity-60")}>
    <span className={cn("text-[14px] font-medium", label === "liked" ? "text-emerald-700" : "text-red-700")}>{title}</span>
    <span className="text-[12px] text-muted-foreground">Drop images here or click to choose (PNG, JPEG, WEBP, GIF, HEIC)</span>
    <input type="file" multiple accept="image/*,.heic" className="sr-only" disabled={disabled} onChange={(e) => { pick(e.target.files); e.target.value = ""; }} aria-label={title} />
  </label>;
}

export function ConnectAgent({ id }: { id: string }) {
  const cli = `stash image-eval check ${id} drawing.png --caller my-agent --task "what it is for"`;
  const origin = typeof window === "undefined" ? "https://api.joinstash.ai" : window.location.origin;
  const curl = `curl -H "Authorization: Bearer $STASH_API_KEY" \\\n  -F file=@drawing.png -F caller=my-agent -F task="what it is for" \\\n  ${origin}/api/v1/image-evals/${id}/score`;
  return <section className="mt-6 rounded-md border border-border px-4 py-3">
    <h2 className="m-0 text-[15px] font-semibold">Connect your agent</h2>
    <p className="mt-1 text-[13px] text-muted-foreground">Tell your agent to check each draft and fix what comes back. Each call returns a score from 0 to 1 and the most important fixes, and shows up below. MCP agents can use the <code>stash_image_eval_score</code> tool.</p>
    <pre className="mt-2 overflow-x-auto rounded bg-surface/60 p-3 text-[12px]">{cli}</pre>
    <pre className="mt-2 overflow-x-auto rounded bg-surface/60 p-3 text-[12px]">{curl}</pre>
  </section>;
}

function Calls({ id, calls, onLabel }: { id: string; calls: ImageEvalCall[]; onLabel: (callId: string, label: ImageEvalLabel | null, note: string) => void }) {
  const runs = useMemo(() => {
    const byTask = new Map<string, ImageEvalCall[]>();
    for (const call of [...calls].reverse()) {
      const key = `${call.caller}\u0000${call.task}`;
      byTask.set(key, [...(byTask.get(key) ?? []), call]);
    }
    return [...byTask.values()].filter((cs) => cs.length > 1);
  }, [calls]);
  return <section className="mt-8">
    <h2 className="m-0 mb-3 text-[15px] font-semibold">Agent calls</h2>
    {calls.length === 0 && <EmptyState title="No calls yet">When an agent scores an image, it appears here with the score and the fixes it was given.</EmptyState>}
    {runs.length > 0 && <div className="mb-4 rounded-md border border-border px-4 py-3">
      <h3 className="m-0 mb-2 text-[13px] font-semibold">Score across each agent&apos;s drafts</h3>
      {runs.map((cs) => <div key={cs[0].id} className="flex flex-wrap items-center gap-2 py-1 text-[12px]">
        <span className="w-64 truncate text-muted-foreground" title={cs[0].task}>{cs[0].caller} · {cs[0].task || "untitled"}</span>
        <span className="font-mono">{cs.map((c) => c.score.toFixed(2)).join(" → ")}</span>
      </div>)}
    </div>}
    <div className="divide-y divide-border rounded-md border border-border">
      {calls.map((call) => <CallRow key={call.id} id={id} call={call} onLabel={onLabel} />)}
    </div>
  </section>;
}

function CallRow({ id, call, onLabel }: { id: string; call: ImageEvalCall; onLabel: (callId: string, label: ImageEvalLabel | null, note: string) => void }) {
  const [note, setNote] = useState(call.feedback_note ?? "");
  const c = call.comments;
  return <div className="grid gap-4 px-4 py-3 md:grid-cols-[180px_1fr_220px]">
    <ImageEvalImage path={imageEvalCallImagePath(id, call.id)} alt={`Image scored for ${call.task || "a call"}`} className="h-44 w-44" />
    <div className="min-w-0 text-[13px]">
      <div className="text-[12px] text-muted-foreground">{relativeTime(call.created_at)} · {call.caller || "unknown caller"}{call.task && ` · ${call.task}`}</div>
      <div className="mt-1"><span className="text-[20px] font-semibold">{call.score.toFixed(2)}</span></div>
      {c?.summary && <p className="mt-1">{c.summary}</p>}
      {c && c.fixes.length > 0 && <ol className="mt-1 list-decimal space-y-1 pl-5">{c.fixes.map((f, i) => <li key={i}><span className="font-medium">{f.issue}</span> <span className="text-muted-foreground">{f.fix}</span></li>)}</ol>}
      {c && c.keep.length > 0 && <p className="mt-1 text-[12px] text-muted-foreground">Keep: {c.keep.join("; ")}</p>}
    </div>
    <div className="flex flex-col gap-2 text-[12px]">
      <div className="flex gap-2">
        <Button size="sm" variant={call.feedback_label === "liked" ? "default" : "outline"} onClick={() => onLabel(call.id, call.feedback_label === "liked" ? null : "liked", note)}>I like it</Button>
        <Button size="sm" variant={call.feedback_label === "disliked" ? "default" : "outline"} onClick={() => onLabel(call.id, call.feedback_label === "disliked" ? null : "disliked", note)}>I don&apos;t</Button>
      </div>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000} placeholder="What's off? (optional; agents see these notes in later fixes)"
        aria-label="Note on this image" className="rounded-md border border-border bg-background p-2" />
      {call.feedback_label && <span className="text-muted-foreground">Added as a {call.feedback_label} example</span>}
    </div>
  </div>;
}

function Examples({ id, examples, onDelete }: { id: string; examples: ImageEvalExample[]; onDelete: (exampleId: string) => void }) {
  if (examples.length === 0) return null;
  return <section className="mt-8">
    <h2 className="m-0 mb-3 text-[15px] font-semibold">Examples</h2>
    {(["liked", "disliked", "imitation"] as const).map((group) => <div key={group} className="mb-5">
      <h3 className="m-0 mb-2 text-[13px] font-semibold">{group === "liked" ? "Liked" : group === "disliked" ? "Disliked" : "Imitations (drawn by Stash, treated as not quite)"}</h3>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
        {examples.filter((e) => (group === "imitation" ? e.source === "imitation" : e.label === group && e.source !== "imitation")).map((e) => {
          const label = e.label;
          const wrong = e.heldout_score != null && (e.heldout_score >= 0.5) !== (label === "liked");
          return <div key={e.id} className="text-[11px]">
            <ImageEvalImage path={imageEvalExampleImagePath(id, e.id)} alt={e.filename || "example"} className="h-28 w-full" />
            <div className="mt-1 flex items-center justify-between gap-1">
              <span className={cn("truncate", wrong ? "text-red-600" : "text-muted-foreground")} title={wrong ? "Misjudged when held out" : e.filename}>
                {e.heldout_score != null ? `held-out ${e.heldout_score.toFixed(2)}` : e.source === "call" ? "from a call" : "untrained"}
              </span>
              <button type="button" className="text-muted-foreground hover:text-red-600" onClick={() => onDelete(e.id)} aria-label={`Remove ${e.filename || "example"}`}>Remove</button>
            </div>
          </div>;
        })}
      </div>
    </div>)}
  </section>;
}

const GROUPS = [
  { key: "liked", label: "of your images recognized" },
  { key: "imitation", label: "of near-miss imitations rejected" },
  { key: "disliked", label: "of the images you marked as not the style rejected" },
  { key: "offstyle", label: "of clearly off-style images rejected" },
] as const;

/** How the eval did on examples it did not train on, per kind of example. */
export function Quality({ detail, compact = false }: { detail: Pick<Detail, "heldout_accuracy" | "heldout_by_group">; compact?: boolean }) {
  const by = detail.heldout_by_group;
  if (!by) return <div><span className="text-[26px] font-semibold">{Math.round((detail.heldout_accuracy ?? 0) * 100)}%</span> <span className="text-[13px] text-muted-foreground">right on examples it did not train on</span></div>;
  const rows = GROUPS.filter((g) => by[g.key] != null);
  const weak = rows.filter((g) => (by[g.key] ?? 1) < 0.8);
  return <div className={compact ? "space-y-0.5 text-xs" : "w-full space-y-1 text-[13px]"}>
    <div className="text-muted-foreground">On examples it didn&apos;t train on:</div>
    {rows.map((g) => <div key={g.key}><span className="font-semibold tabular-nums">{Math.round((by[g.key] ?? 0) * 100)}%</span> {g.label}</div>)}
    {weak.length > 0 && <div className="text-amber-600">Weak spot: {weak.map((g) => g.label.replace(/^of /, "")).join("; ")}. Add more examples, or treat its scores there with care.</div>}
  </div>;
}
