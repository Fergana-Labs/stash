"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Picture } from "@/components/taste/website-eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { tasteHillClimb, tasteHillClimbState, type HillClimbArm, type HillClimbState, type TasteWorkspace } from "@/lib/taste-api";
import { ScoreBar, Section, percent } from "./TasteSections";

export const DEFAULT_BRIEF =
  "Build the Recent sessions page for Relay, a tool that keeps a searchable history of your coding-agent sessions. Show the user's recent sessions with title, project, agent, model, timestamp, and status, with filters.";

const POLL_MS = 2000;

function Arm({ title, sub, arm, threshold, graded }: { title: string; sub: string; arm: HillClimbArm; threshold: number; graded: boolean }) {
  const rounds = arm.rounds;
  const [pick, setPick] = useState<number | null>(null);
  const shown = rounds.find((r) => r.round === pick) ?? rounds[rounds.length - 1];
  const approved = rounds.some((r) => r.approved);
  return (
    <div className="min-w-0">
      <header className="mb-2 flex items-baseline gap-2">
        <h3 className="m-0 text-[12.5px] font-semibold">{title}</h3>
        <span className="min-w-0 truncate text-[11.5px] text-muted-foreground">{sub}</span>
        <span className="flex-1" />
        {graded && approved && <span className="flex shrink-0 items-center gap-1 text-[11.5px] text-emerald-700 dark:text-emerald-400"><Check className="size-3.5" />Approved</span>}
      </header>
      <div className="relative aspect-[3/2] overflow-hidden rounded border border-border bg-surface">
        {shown ? <Picture key={shown.screenshot_sha256} kind="check" id={shown.screenshot_sha256} alt={`${title}, round ${shown.round}`} className="h-full" /> : (
          <div className="flex h-full items-center justify-center gap-2 text-[12px] text-muted-foreground"><Loader2 className="size-4 animate-spin" />{arm.working ?? "Starting"}…</div>
        )}
        {shown && arm.status === "running" && arm.working && (
          <span className="absolute bottom-2 left-2 flex items-center gap-1.5 rounded bg-background/90 px-2 py-1 text-[11px] text-muted-foreground shadow-sm"><Loader2 className="size-3 animate-spin" />{arm.working}</span>
        )}
      </div>
      <ol className="m-0 mt-2 flex list-none gap-1.5 p-0">
        {rounds.map((r) => (
          <li key={r.round}>
            <button type="button" onClick={() => setPick(r.round)} className={cn("flex items-center gap-1.5 rounded border px-2 py-1 font-mono text-[11px] tabular-nums", shown?.round === r.round ? "border-foreground/40 bg-surface" : "border-border hover:bg-surface/60")} aria-label={`Round ${r.round}, score ${percent(r.score)}`}>
              <span className="text-muted-foreground">{r.round}</span>
              <span className={cn(r.score >= threshold ? "text-emerald-700 dark:text-emerald-400" : r.score >= 0.4 ? "text-amber-700 dark:text-amber-400" : "text-red-600 dark:text-red-400")}>{percent(r.score)}</span>
            </button>
          </li>
        ))}
      </ol>
      {shown && (
        <div className="mt-2 space-y-1.5 text-[12.5px]">
          <ScoreBar score={shown.score} />
          <p className="m-0">{shown.summary}</p>
          {graded && !shown.approved && shown.fixes.length > 0 && (
            <div>
              <h4 className="m-0 mb-1 text-[11.5px] font-medium text-muted-foreground">Grader feedback sent to the agent</h4>
              <ol className="m-0 space-y-1 pl-4 text-[12px]">{shown.fixes.map((f) => <li key={f.issue}>{f.issue}<span className="block text-muted-foreground">→ {f.fix}</span></li>)}</ol>
            </div>
          )}
          {!graded && rounds.length > 1 && <p className="m-0 text-[11.5px] text-muted-foreground">Told only “make it look better” between rounds. Scores are from your grader, which this agent never sees.</p>}
        </div>
      )}
      {arm.status === "failed" && <p role="alert" className="m-0 mt-2 text-[12px] text-destructive">{arm.error || "This agent failed."}</p>}
    </div>
  );
}

/** Live: the same agent builds the same page with and without the user's grader in the loop. */
export default function HillClimbSection({ data }: { data: TasteWorkspace }) {
  const latest = data.jobs.find((j) => j.operation === "hillclimb");
  const [jobId, setJobId] = useState<string | null>(null);
  const [state, setState] = useState<HillClimbState | null>(null);
  const [brief, setBrief] = useState(DEFAULT_BRIEF);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const active = jobId ?? latest?.id ?? null;

  useEffect(() => {
    if (!active) return;
    let live = true;
    const load = () => tasteHillClimbState(active).then((s) => { if (live) setState(s); }).catch(() => {});
    void load();
    const timer = setInterval(() => void load(), POLL_MS);
    return () => { live = false; clearInterval(timer); };
  }, [active]);

  const running = state?.status === "running" || (!!latest && ["queued", "running"].includes(latest.status) && !state);
  const start = async () => {
    setStarting(true); setError("");
    try { const r = await tasteHillClimb(brief); setState(null); setJobId(r.job_id); }
    catch (e) { setError(errorMessage(e)); }
    finally { setStarting(false); }
  };

  return (
    <Section
      title="Hill-climb a website"
      meta="Same agent, same brief: with your grader in the loop, and without"
      actions={<Button size="sm" disabled={starting || running || !brief.trim()} onClick={() => void start()}>{starting || running ? <Loader2 className="animate-spin" /> : <Play />}{running ? "Running" : state ? "Run again" : "Start"}</Button>}
    >
      <label className="block">
        <span className="sr-only">Brief</span>
        <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={2} disabled={running} className="w-full resize-none rounded border border-border bg-background px-2.5 py-1.5 text-[12.5px] leading-5 outline-none focus:border-foreground/40" />
      </label>
      <p className="m-0 mt-1 text-[11.5px] text-muted-foreground">The agent is told: build this, check it with the grader, and keep revising until the grader approves it ({state ? percent(state.threshold) : 80}+).</p>
      {error && <p role="alert" className="m-0 mt-2 text-[12px] text-destructive">{error}</p>}
      {state && (
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          <Arm title="With your grader" sub="sees the grader’s feedback each round" arm={state.arms.grader} threshold={state.threshold} graded />
          <Arm title="Without" sub="same agent, no grader" arm={state.arms.alone} threshold={state.threshold} graded={false} />
        </div>
      )}
    </Section>
  );
}
