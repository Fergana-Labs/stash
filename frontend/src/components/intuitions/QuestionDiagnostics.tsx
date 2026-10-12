"use client";

import { cn } from "@/lib/utils";
import type { Head, QuestionDiagnostics as Diagnostics, RubricQuestion } from "@/lib/intuition-api";
import { byLabelAnswers, num, separatingOption, pct, questionImportance, questionVerdict, type QuestionVerdict } from "./im-helpers";
import { Bar } from "./im-ui";

const TYPE_LABEL: Record<RubricQuestion["type"], string> = { noul: "yes/no", choice: "choice", score: "score" };

const VERDICT: Record<QuestionVerdict, { label: string; className: string; hint?: string }> = {
  helps: { label: "helps", className: "tag-success" },
  calibration: { label: "sharpens confidence", className: "tag-muted", hint: "Same accuracy without it, but worse calibrated." },
  none: { label: "no held-out gain", className: "tag-warning", hint: "Doesn’t help on held-out — rewrite or remove." },
  hurts: { label: "hurts held-out", className: "tag-warning", hint: "The head does better without it — rewrite or remove." },
};

function points(value: number | null | undefined): string {
  if (value == null) return "—";
  const p = value * 100;
  return `${p > 0 ? "+" : p < 0 ? "−" : "±"}${Math.abs(p).toFixed(1)} pts`;
}

function signedNum(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : value < 0 ? "−" : "±"}${Math.abs(value).toFixed(3)}`;
}

/**
 * Per-question diagnostics from the last fit: how the judge's answers differ by label,
 * how much the head leans on each question, and what held-out accuracy / log loss
 * look like when the head is refitted without it.
 */
export default function QuestionDiagnostics({
  diagnostics,
  rubric,
  head,
  labelOrder,
}: {
  diagnostics: Diagnostics | null | undefined;
  rubric: RubricQuestion[];
  head: Head | null;
  labelOrder: string[];
}) {
  if (!diagnostics) return <p className="m-0 text-[12px] text-muted-foreground">Fit the draft to see diagnostics. Hand-edited heads and older fits don’t have them.</p>;
  const importance = questionImportance(head, rubric);
  const maxImportance = Math.max(1e-9, ...importance.values());
  const byId = new Map(diagnostics.questions.map((q) => [q.question_id, q]));
  const rows = rubric.filter((q) => byId.has(q.id));
  const base = diagnostics.baseline;

  return (
    <div className="space-y-2">
      <p className="m-0 max-w-3xl text-[12px] leading-relaxed text-muted-foreground">
        {base ? (
          <>
            Held-out with every question: accuracy <span className="font-mono text-foreground">{pct(base.accuracy, 1)}</span>, log loss <span className="font-mono text-foreground">{num(base.log_loss)}</span>. Each row
            refits the head without that question and reports what that costs on held-out examples. Mean answers are over the fitted examples, by label: a question whose answers barely differ between
            labels can’t separate them.
          </>
        ) : (
          <>Too few held-out examples to measure what each question is worth; mean answers by label are shown. Move more labeled examples to held-out and refit.</>
        )}
      </p>
      <div className="overflow-x-auto rounded-md border border-border-subtle">
        <table className="w-full min-w-[46rem] border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border-subtle bg-surface/60 text-left text-[10.5px] tracking-wide text-muted-foreground uppercase">
              <th className="px-3 py-1.5 font-medium">Question</th>
              <th className="w-28 px-3 py-1.5 font-medium" title="Spread of the head's weights on this question's answers across labels">
                Weight
              </th>
              <th className="w-56 px-3 py-1.5 font-medium" title="Yes/no: P(yes). Choice and score: the share of the option that best separates the labels; hover a row for every option.">
                Mean answer by label
              </th>
              <th className="w-24 px-3 py-1.5 text-right font-medium" title="Held-out accuracy lost when the head is refitted without this question">
                Acc. lost w/o
              </th>
              <th className="w-24 px-3 py-1.5 text-right font-medium" title="Held-out log loss added when the head is refitted without this question">
                Log loss w/o
              </th>
              <th className="w-44 px-3 py-1.5 font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((q) => {
              const d = byId.get(q.id)!;
              const weight = importance.get(q.id) ?? 0;
              const verdict = questionVerdict(d.ablation);
              const answers = byLabelAnswers(q, q.id, d.by_label, labelOrder);
              const sepKey = separatingOption(answers);
              const drop = d.ablation?.accuracy_drop;
              const rise = d.ablation?.log_loss_rise;
              return (
                <tr key={q.id} className="border-b border-border-subtle align-top last:border-b-0">
                  <td className="px-3 py-2">
                    <div className="line-clamp-2 text-[12px] leading-snug text-foreground" title={q.prompt}>
                      {q.prompt}
                    </div>
                    <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[10.5px] text-muted-foreground">
                      <span className="truncate">{q.id}</span>
                      <span className="tag tag-muted shrink-0 normal-case">{TYPE_LABEL[q.type]}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    {head ? (
                      <div className="flex items-center gap-2 pt-1">
                        <Bar value={weight / maxImportance} className="w-12" />
                        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">{weight.toFixed(2)}</span>
                      </div>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <ul className="m-0 list-none space-y-0.5 p-0">
                      {answers.map((row) => (
                        <li key={row.label} className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-center gap-2">
                          <span className="truncate font-mono text-[11px] text-dim" title={row.label}>
                            {row.label}
                          </span>
                          {q.type === "noul" ? (
                            <span className="flex items-center gap-1.5">
                              <Bar value={row.values[0]?.value ?? 0} tone={(row.values[0]?.value ?? 0) >= 0.5 ? "brand" : "muted"} className="w-16" />
                              <span className="font-mono text-[11px] text-muted-foreground tabular-nums">{pct(row.values[0]?.value)}</span>
                            </span>
                          ) : (
                            <span className="flex min-w-0 items-center gap-1.5" title={row.values.map((v) => `${v.text} ${pct(v.value)}`).join(" · ")}>
                              <Bar value={row.values.find((v) => v.key === sepKey)?.value ?? 0} className="w-16 shrink-0" />
                              <span className="truncate font-mono text-[11px] text-muted-foreground tabular-nums">
                                {pct(row.values.find((v) => v.key === sepKey)?.value)} <span className="text-dim">{sepKey}</span>
                              </span>
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </td>
                  <td
                    className={cn(
                      "px-3 py-2 text-right font-mono tabular-nums",
                      drop == null ? "text-muted-foreground" : drop > 0 ? "text-emerald-700 dark:text-emerald-400" : drop < 0 ? "text-yellow-700 dark:text-yellow-400" : "text-muted-foreground",
                    )}
                  >
                    {points(drop)}
                  </td>
                  <td className={cn("px-3 py-2 text-right font-mono tabular-nums", rise != null && rise > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground")}>{signedNum(rise)}</td>
                  <td className="px-3 py-2">
                    {verdict ? (
                      <>
                        <span className={cn("tag normal-case", VERDICT[verdict].className)}>{VERDICT[verdict].label}</span>
                        {VERDICT[verdict].hint && <p className="m-0 mt-1 text-[11px] leading-snug text-muted-foreground">{VERDICT[verdict].hint}</p>}
                      </>
                    ) : (
                      <span className="text-[11px] text-muted-foreground">Needs more held-out examples</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="m-0 text-[11px] text-muted-foreground">
        Positive numbers mean the question earns its place: removing it loses accuracy or raises log loss. Held-out sets are small, so treat single-example swings with care.
      </p>
    </div>
  );
}
