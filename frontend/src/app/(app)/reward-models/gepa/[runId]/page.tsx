"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState, type ReactNode } from "react";
import { ArrowLeft, Check, Copy, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { RmPageSkeleton } from "@/components/reward-models/RmSkeletons";
import { StatusBadge, isActiveJob, pendingSkillTitle } from "@/components/reward-models/rm-ui";
import { diffLines, errorMessage, formatScore, relativeTime, skillFirstLine } from "@/components/reward-models/rm-text";
import { JobError } from "@/components/reward-models/JobError";
import { rmCreateGepaRun, rmDownloadSkill, rmGetGepaRun, rmGetRewardModel } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RmGepaCandidate, RmGepaRun, RmRewardModel } from "@/lib/types";

const POLL_MS = 3000;

type CompareView = "side" | "diff";

export default function GepaRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);
  const [run, setRun] = useState<RmGepaRun | null>(null);
  const [model, setModel] = useState<RmRewardModel | null>(null);
  useBreadcrumbs(
    [
      { label: "Reward models", href: "/reward-models/models" },
      { label: run?.skill_name ?? "Skill" },
    ],
    `rm-gepa-${runId}-${run?.skill_name ?? ""}`,
  );

  const load = useCallback(async () => {
    try {
      setRun(await rmGetGepaRun(runId));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const rewardModelId = run?.reward_model_id ?? null;
  useEffect(() => {
    if (rewardModelId === null) return;
    rmGetRewardModel(rewardModelId)
      .then(setModel)
      .catch((e) => toast.error(errorMessage(e)));
  }, [rewardModelId]);

  const polling = run !== null && isActiveJob(run.status);
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [polling, load]);

  async function retry() {
    if (run === null) return;
    setRetrying(true);
    try {
      const next = await rmCreateGepaRun({ reward_model_id: run.reward_model_id });
      router.push(`/reward-models/gepa/${next.id}`);
    } catch (e) {
      toast.error(errorMessage(e));
      setRetrying(false);
    }
  }

  if (run === null || model === null) return <RmPageSkeleton />;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl px-10 pt-6 pb-16">
        <Link href="/reward-models/models" className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to reward models
        </Link>
        <div className="mt-3 flex items-center gap-3">
          {run.skill_name !== null ? (
            <h1 className="m-0 font-mono text-[20px] font-semibold tracking-tight text-foreground">{run.skill_name}</h1>
          ) : (
            <h1 className="m-0 font-display text-[20px] font-semibold tracking-tight text-muted-foreground">
              {pendingSkillTitle(run.status)}
            </h1>
          )}
          <StatusBadge status={run.status} />
          <span className="text-[12px] text-muted-foreground">started {relativeTime(run.created_at)}</span>
        </div>
        {run.skill_description !== null && (
          <p className="m-0 mt-1.5 max-w-3xl text-[13px] leading-relaxed text-dim">{run.skill_description}</p>
        )}
        <div className="mt-2 flex flex-wrap gap-x-4 font-mono text-[11.5px] text-muted-foreground">
          <span>reward model {model.name}</span>
          <span>task {run.task_model}</span>
          {run.task_api_base && <span>@ {run.task_api_base}</span>}
          <span>reflection {run.reflection_model}</span>
          <span>{run.max_metric_calls} metric calls</span>
        </div>

        {run.status === "failed" && run.error && (
          <div className="mt-5">
            <JobError error={run.error} />
            <Button className="mt-3" onClick={() => void retry()} disabled={retrying}>{retrying ? "Starting…" : "Retry generation"}</Button>
          </div>
        )}

        {run.seed_score !== null && run.best_score !== null && (
          <ScoreSummary seed={run.seed_score} best={run.best_score} candidates={run.candidates?.length ?? 0} />
        )}

        {run.best_skill !== null ? (
          <BestSkill runId={run.id} skill={run.best_skill} />
        ) : (
          isActiveJob(run.status) && (
            <p className="mt-6 flex items-center gap-2 text-[12.5px] text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Writing skill… with reward model <span className="font-medium text-foreground">{model.name}</span>. The SKILL.md
              appears here when the run finishes.
            </p>
          )
        )}

        {run.seed_skill !== null && run.best_skill !== null && <SkillComparison seed={run.seed_skill} best={run.best_skill} />}

        {run.candidates && run.candidates.length > 0 && <Candidates candidates={run.candidates} best={run.best_skill} />}
      </div>
    </div>
  );
}

function BestSkill({ runId, skill }: { runId: string; skill: string }) {
  const [downloading, setDownloading] = useState(false);

  async function download() {
    setDownloading(true);
    try {
      const text = await rmDownloadSkill(runId);
      const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "SKILL.md";
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="mt-8">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="sys-label m-0">Best skill (SKILL.md)</h2>
        <div className="flex gap-1.5">
          <CopyButton text={skill} />
          <Button size="sm" onClick={() => void download()} disabled={downloading}>
            {downloading ? <Loader2 className="animate-spin" /> : <Download />}
            Download SKILL.md
          </Button>
        </div>
      </div>
      <pre className="scroll-thin m-0 max-h-[640px] overflow-auto rounded-lg border border-green-600/25 bg-surface/50 px-4 py-3.5 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-foreground">
        {skill}
      </pre>
    </section>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <Button variant="outline" size="sm" onClick={() => void copy()}>
      {copied ? <Check /> : <Copy />}
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

function ScoreSummary({ seed, best, candidates }: { seed: number; best: number; candidates: number }) {
  const delta = best - seed;
  return (
    <div className="mt-6 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border bg-border">
      <Stat label="Seed score" value={formatScore(seed)} />
      <Stat
        label="Best score"
        value={formatScore(best)}
        detail={
          <span className={delta > 0 ? "text-green-700 dark:text-green-400" : "text-muted-foreground"}>
            {delta >= 0 ? "+" : ""}
            {formatScore(delta)}
          </span>
        }
        emphasis
      />
      <Stat label="Candidates tried" value={String(candidates)} />
    </div>
  );
}

function Stat({ label, value, detail, emphasis }: { label: string; value: string; detail?: ReactNode; emphasis?: boolean }) {
  return (
    <div className="bg-background px-4 py-3">
      <div className="text-[10.5px] tracking-wide text-muted-foreground uppercase">{label}</div>
      <div className="mt-1 flex items-baseline gap-2 font-mono tabular-nums">
        <span className={emphasis ? "text-[22px] font-semibold text-foreground" : "text-[18px] text-foreground"}>{value}</span>
        {detail && <span className="text-[12.5px]">{detail}</span>}
      </div>
    </div>
  );
}

function SkillComparison({ seed, best }: { seed: string; best: string }) {
  const [view, setView] = useState<CompareView>("diff");
  return (
    <section className="mt-8">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="sys-label m-0">Seed vs best skill</h2>
        <div className="flex rounded-md border border-border p-0.5 text-[12px]">
          {(["side", "diff"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={cn(
                "cursor-pointer rounded px-2 py-0.5 transition-colors",
                view === v ? "bg-raised font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {v === "side" ? "Side by side" : "Diff"}
            </button>
          ))}
        </div>
      </div>
      {view === "side" ? (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1 text-[11.5px] font-medium text-muted-foreground">Seed</div>
            <SkillBlock text={seed} />
          </div>
          <div>
            <div className="mb-1 text-[11.5px] font-medium text-green-700 dark:text-green-400">Best</div>
            <SkillBlock text={best} />
          </div>
        </div>
      ) : (
        <DiffBlock before={seed} after={best} />
      )}
    </section>
  );
}

function SkillBlock({ text }: { text: string }) {
  return (
    <pre className="scroll-thin m-0 max-h-[480px] overflow-auto rounded-lg border border-border bg-surface/50 px-3.5 py-3 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-foreground">
      {text}
    </pre>
  );
}

function DiffBlock({ before, after }: { before: string; after: string }) {
  return (
    <div className="scroll-thin max-h-[560px] overflow-auto rounded-lg border border-border bg-surface/30 py-2 font-mono text-[12.5px] leading-relaxed">
      {diffLines(before, after).map((line, i) => (
        <div
          key={i}
          className={cn(
            "flex px-3 whitespace-pre-wrap",
            line.kind === "add" && "bg-green-500/12 text-green-800 dark:text-green-300",
            line.kind === "del" && "bg-red-500/10 text-red-700 line-through decoration-red-500/40 dark:text-red-300",
            line.kind === "same" && "text-dim",
          )}
        >
          <span className="w-5 shrink-0 text-muted-foreground select-none">
            {line.kind === "add" ? "+" : line.kind === "del" ? "−" : ""}
          </span>
          <span className="min-w-0 flex-1">{line.text === "" ? " " : line.text}</span>
        </div>
      ))}
    </div>
  );
}

function Candidates({ candidates, best }: { candidates: RmGepaCandidate[]; best: string | null }) {
  const [open, setOpen] = useState<number | null>(null);
  const ranked = candidates.map((c, i) => ({ ...c, tried: i + 1 })).sort((a, b) => b.score - a.score);
  const top = ranked[0].score;
  const bottom = ranked[ranked.length - 1].score;
  // Reward scores are unbounded logits, so bars are scaled between the worst and best candidate.
  const barWidth = (score: number) => (top === bottom ? 100 : 6 + ((score - bottom) / (top - bottom)) * 94);

  return (
    <section className="mt-8">
      <h2 className="sys-label m-0 mb-2">Candidates ({candidates.length})</h2>
      <div className="overflow-hidden rounded-lg border border-border">
        {ranked.map((c) => (
          <div key={c.tried} className="border-b border-border-subtle last:border-b-0">
            <button
              type="button"
              onClick={() => setOpen(open === c.tried ? null : c.tried)}
              className="flex w-full cursor-pointer items-center gap-3 px-3 py-2 text-left hover:bg-surface/60"
            >
              <span className="w-8 font-mono text-[11px] text-muted-foreground tabular-nums">#{c.tried}</span>
              <span className="w-16 font-mono text-[12.5px] text-foreground tabular-nums">{formatScore(c.score)}</span>
              <span className="h-1.5 w-24 overflow-hidden rounded-full bg-raised">
                <span
                  className="block h-full rounded-full bg-brand-500/70"
                  style={{ width: `${barWidth(c.score)}%` }}
                />
              </span>
              <span className="min-w-0 flex-1 truncate text-[12.5px] text-dim">{skillFirstLine(c.skill)}</span>
              {c.skill === best && <span className="tag tag-success">best</span>}
            </button>
            {open === c.tried && (
              <div className="px-3 pb-3">
                <SkillBlock text={c.skill} />
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
