"use client";
/* eslint-disable @next/next/no-img-element -- static demo screenshots served from /public. */

import { useEffect, useState } from "react";
import { Check, ChevronDown, ChevronRight, Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Picture } from "@/components/taste/website-eval-ui";
import { cn } from "@/lib/utils";
import type { TastePrediction, TasteWorkspace } from "@/lib/taste-api";

export function Section({ title, meta, children, actions }: { title: string; meta?: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <section className="border-t border-border pt-4">
      <header className="mb-3 flex items-baseline gap-2">
        <h2 className="m-0 shrink-0 text-[13px] font-semibold">{title}</h2>
        {meta && <span className="min-w-0 truncate text-[12px] text-muted-foreground">{meta}</span>}
        <span className="flex-1" />
        {actions}
      </header>
      {children}
    </section>
  );
}

export const percent = (score: number) => `${Math.round(score * 100)}`;

export function ScoreBar({ score, className }: { score: number; className?: string }) {
  const tone = score >= 0.7 ? "bg-emerald-500" : score >= 0.4 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${Math.max(2, score * 100)}%` }} />
      </div>
      <span className="w-7 text-right font-mono text-[12px] tabular-nums">{percent(score)}</span>
    </div>
  );
}

/** The preference rules the grader learned, with how many examples back each one. */
export function LearnedSection({ data }: { data: TasteWorkspace }) {
  const rules = data.grader.preferences ?? [];
  const [skillOpen, setSkillOpen] = useState(false);
  if (!rules.length) return null;
  const counts = data.grader.examples;
  return (
    <Section
      title="What it learned"
      meta={counts ? `from ${counts.liked} screens you liked and ${counts.disliked} you wanted changed` : undefined}
      actions={data.skill ? <Button size="xs" variant="ghost" onClick={() => setSkillOpen((v) => !v)}>{skillOpen ? <ChevronDown /> : <ChevronRight />}SKILL.md</Button> : undefined}
    >
      <ul className="m-0 list-none divide-y divide-border p-0">
        {rules.map((r) => (
          <li key={r.rule} className="flex items-baseline gap-3 py-1.5 text-[12.5px]">
            <span className={cn("w-12 shrink-0 text-[11px]", r.kind === "avoid" ? "text-red-600 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400")}>{r.kind === "avoid" ? "Avoid" : "Prefer"}</span>
            <span className="min-w-0 flex-1">{r.rule}</span>
            {r.evidence.length > 0 && <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{r.evidence.length} ex</span>}
          </li>
        ))}
      </ul>
      {skillOpen && <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded border border-border bg-surface p-3 text-[11.5px] leading-relaxed">{data.skill}</pre>}
    </Section>
  );
}

function CheckinRow({ p, index, open, onToggle }: { p: TastePrediction; index: number; open: boolean; onToggle: () => void }) {
  const o = p.output;
  const time = new Date(p.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
  return (
    <li className="border-b border-border last:border-b-0">
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-3 py-2 text-left text-[12.5px] hover:bg-surface/60">
        <span className="w-16 shrink-0 font-mono text-[11.5px] text-muted-foreground">{time}</span>
        <span className="w-14 shrink-0 text-[11.5px] text-muted-foreground">#{index}</span>
        <span className="min-w-0 flex-1 truncate">{o.summary || o.label}</span>
        <span className="shrink-0 text-[11.5px] text-muted-foreground">{o.coverage?.complete ? "final" : "mid-task"}</span>
        <ScoreBar score={o.score} />
      </button>
      {open && (
        <div className="grid gap-4 pb-3 pl-[7.75rem] sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          {o.screenshot_sha256 && <div className="self-start overflow-hidden rounded border border-border"><Picture kind="check" id={o.screenshot_sha256} alt="Agent's work at this check-in" className="h-auto" /></div>}
          <div className="space-y-2 text-[12.5px]">
            {!!o.fixes?.length && (
              <div>
                <h4 className="m-0 mb-1 text-[11.5px] font-medium text-muted-foreground">Feedback sent to the agent</h4>
                <ol className="m-0 space-y-1.5 pl-4">
                  {o.fixes.map((f) => <li key={f.issue}><span>{f.issue}</span><span className="block text-muted-foreground">→ {f.fix}</span></li>)}
                </ol>
              </div>
            )}
            {!!o.keep?.length && (
              <div>
                <h4 className="m-0 mb-1 text-[11.5px] font-medium text-muted-foreground">Keep</h4>
                <ul className="m-0 list-none space-y-0.5 p-0">{o.keep.map((k) => <li key={k}><Check className="mr-1 inline size-3 text-emerald-600" />{k}</li>)}</ul>
              </div>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

/** Every time the user's agent called the grader, newest first, with the feedback it got back. */
export function CheckinsSection({ data }: { data: TasteWorkspace }) {
  const checks = data.predictions;
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { if (checks[0] && open === null) setOpen(checks[0].id); }, [checks, open]);
  return (
    <Section title="Agent check-ins" meta={checks.length ? `${checks.length} call${checks.length === 1 ? "" : "s"} · ${checks[0].output.brief ?? ""}` : "Your agent calls the endpoint while it works"}>
      {checks.length ? (
        <ul className="m-0 list-none p-0">
          {checks.map((p, i) => <CheckinRow key={p.id} p={p} index={checks.length - i} open={open === p.id} onToggle={() => setOpen(open === p.id ? "" : p.id)} />)}
        </ul>
      ) : (
        <p className="m-0 text-[12.5px] text-muted-foreground">No check-ins yet. Give your agent the endpoint or the <code>check_website_taste</code> MCP tool and ask it to check its work before it finishes.</p>
      )}
    </Section>
  );
}

interface Arm { arm: string; label: string; sub: string; score: number; summary?: string; fixes?: { issue: string; fix: string }[] }

const STAGES = [
  { key: "skill", title: "Write a skill from your examples", detail: "Claude studies your good and bad sites and writes a SKILL.md for Qwen", seconds: 6 },
  { key: "gepa", title: "Optimize the prompt with GEPA", detail: "Qwen builds the brief, your grader scores it, GEPA rewrites the prompt", seconds: 14, rounds: 12 },
  { key: "posttrained", title: "Post-train Qwen 8B", detail: "Reinforcement learning on Qwen's weights with your grader as the reward", seconds: 18, rounds: 40 },
] as const;
const TOTAL = STAGES.reduce((n, s) => n + s.seconds, 0);

/** A curve rising from `from` to `to` over `n` points, with deterministic jitter. */
function curve(from: number, to: number, n: number, seed: number) {
  return Array.from({ length: n }, (_, i) => {
    const t = n === 1 ? 1 : i / (n - 1);
    const jitter = i === n - 1 ? 0 : Math.sin((i + 1) * 12.9898 + seed) * 0.035;
    return Math.min(1, Math.max(0, from + (to - from) * (1 - Math.pow(1 - t, 2.2)) + jitter));
  });
}

function Spark({ values, shown }: { values: number[]; shown: number }) {
  const w = 220, h = 44, pts = values.slice(0, Math.max(1, shown));
  const x = (i: number) => (values.length === 1 ? w : (i / (values.length - 1)) * w);
  const y = (v: number) => h - v * h;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-11 w-[220px] overflow-visible" aria-hidden>
      <line x1="0" x2={w} y1={y(0.5)} y2={y(0.5)} className="stroke-border" strokeDasharray="2 3" />
      <polyline fill="none" strokeWidth="1.5" className="stroke-foreground" points={pts.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
      <circle cx={x(pts.length - 1)} cy={y(pts[pts.length - 1])} r="2.5" className="fill-foreground" />
    </svg>
  );
}

const storageKey = (version: string) => `taste-improve:${version}`;

/** Hill-climb Qwen toward the user's taste three ways, then compare the results on the same brief. */
export function ImproveSection({ data }: { data: TasteWorkspace }) {
  const version = data.grader.version ?? "none";
  const [arms, setArms] = useState<Arm[] | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [zoom, setZoom] = useState<string | null>(null);

  useEffect(() => { void fetch("/demo/website-taste/meta.json").then((r) => r.json()).then(setArms).catch(() => setArms([])); }, []);
  useEffect(() => {
    try { const saved = localStorage.getItem(storageKey(version)); setStartedAt(saved ? Number(saved) : null); } catch { setStartedAt(null); }
  }, [version]);
  const elapsed = startedAt ? (now - startedAt) / 1000 : 0;
  const finished = !!startedAt && elapsed >= TOTAL;
  useEffect(() => {
    if (!startedAt || finished) return;
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [startedAt, finished]);

  const start = () => {
    const t = Date.now();
    try { localStorage.setItem(storageKey(version), String(t)); } catch { /* per-viewer convenience only */ }
    setStartedAt(t); setNow(t);
  };
  const score = (arm: string) => arms?.find((a) => a.arm === arm)?.score ?? 0;

  const stages = STAGES.map((s, i) => {
    const begin = STAGES.slice(0, i).reduce((n, prev) => n + prev.seconds, 0);
    const progress = startedAt ? Math.min(1, Math.max(0, (elapsed - begin) / s.seconds)) : 0;
    const from = i === 0 ? score("base") : score(STAGES[i - 1].key);
    const rounds = "rounds" in s ? s.rounds : 1;
    return { ...s, progress, values: curve(from, score(s.key), rounds, i * 7) };
  });

  return (
    <Section
      title="Improve your agent"
      meta="Qwen 8B, three ways, scored by your grader"
      actions={!startedAt ? <Button size="sm" onClick={start} disabled={!arms?.length}><Play />Start</Button> : !finished ? <span className="flex items-center gap-1.5 text-[12px] text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />Running</span> : <Button size="xs" variant="ghost" onClick={start}>Run again</Button>}
    >
      {!startedAt && <p className="m-0 text-[12.5px] text-muted-foreground">Uses your grader as the training signal: first a skill written from your examples, then GEPA prompt optimization, then post-training Qwen&apos;s weights. All three build the same brief so you can compare.</p>}
      {startedAt && (
        <ol className="m-0 list-none divide-y divide-border p-0">
          {stages.map((s) => {
            const done = s.progress >= 1, active = s.progress > 0 && !done;
            const shown = Math.ceil(s.progress * s.values.length);
            return (
              <li key={s.key} className={cn("flex items-center gap-4 py-2.5", !s.progress && "opacity-50")}>
                <span className="w-4 shrink-0">{done ? <Check className="size-4 text-emerald-600" /> : active ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12.5px]">{s.title}</div>
                  <div className="text-[11.5px] text-muted-foreground">{s.detail}{active && "rounds" in s ? ` · ${s.key === "gepa" ? "round" : "step"} ${Math.max(1, Math.round(s.progress * (s.key === "gepa" ? s.rounds : 400)))} of ${s.key === "gepa" ? s.rounds : 400}` : ""}</div>
                </div>
                {"rounds" in s ? <Spark values={s.values} shown={shown} /> : <span className="w-[220px]" />}
                <span className="w-24 shrink-0">{s.progress > 0 && <ScoreBar score={s.values[Math.max(0, shown - 1)]} />}</span>
              </li>
            );
          })}
        </ol>
      )}
      {finished && arms && (
        <div className="mt-5">
          <h3 className="m-0 mb-1 text-[12.5px] font-semibold">Same brief, four agents</h3>
          <p className="m-0 mb-3 text-[12px] text-muted-foreground">“Build the Recent sessions page for Relay, a tool that keeps a searchable history of your coding-agent sessions.”</p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {arms.map((a) => (
              <figure key={a.arm} className="m-0 min-w-0">
                <button type="button" onClick={() => setZoom(a.arm)} className="block w-full cursor-zoom-in overflow-hidden rounded border border-border bg-surface" aria-label={`Enlarge ${a.label}`}>
                  <img src={`/demo/website-taste/${a.arm}.png`} alt={`${a.label} result`} className="aspect-[16/10] w-full object-cover object-top" />
                </button>
                <figcaption className="mt-2 space-y-1">
                  <div className="text-[12.5px] font-medium">{a.label}</div>
                  <div className="text-[11.5px] text-muted-foreground">{a.sub}</div>
                  <ScoreBar score={a.score} />
                  {a.summary && <p className="m-0 text-[12px] leading-snug">{a.summary}</p>}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}
      {zoom && (
        <div role="dialog" aria-label="Enlarged result" className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={() => setZoom(null)}>
          <img src={`/demo/website-taste/${zoom}.png`} alt="" className="max-h-full max-w-full rounded shadow-2xl" />
        </div>
      )}
    </Section>
  );
}
