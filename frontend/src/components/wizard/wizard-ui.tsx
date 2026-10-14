"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RubricQuestion } from "@/lib/intuition-api";

/** What every card can reach: the model it edits and a way to tell the wizard what happened. */
export interface WizardCtx {
  modelId: string | null;
  /** Post a message into the chat. Cards use kind "event" ("Labeled 12 examples"). */
  send: (text: string, kind?: "message" | "event") => void;
  /** Ask the side panel and other cards to reload model state. */
  refresh: () => void;
  version: number;
  busy: boolean;
}

const Ctx = createContext<WizardCtx>({ modelId: null, send: () => {}, refresh: () => {}, version: 0, busy: false });
export const WizardProvider = Ctx.Provider;
export const useWizard = () => useContext(Ctx);

/** Rubric questions the wizard maintains itself rather than the user. */
export const SIGNAL_IDS = new Set(["verdict", "embedding_probe"]);
export const userCriteria = (rubric: RubricQuestion[]) => rubric.filter((q) => !SIGNAL_IDS.has(q.id));

export function CardShell({ icon: Icon, title, subtitle, actions, children, className }: { icon: LucideIcon; title: string; subtitle?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section aria-label={title} className={cn("my-2 overflow-hidden rounded-lg border border-border bg-background shadow-sm motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 duration-200", className)}>
      <header className="flex items-center gap-2.5 border-b border-border bg-surface/50 px-3.5 py-2.5">
        <span className="grid size-6 shrink-0 place-items-center rounded-md bg-brand-500/10 text-brand-600 dark:text-brand-400"><Icon className="size-3.5" /></span>
        <div className="min-w-0 flex-1">
          <h3 className="m-0 truncate text-[13px] font-semibold">{title}</h3>
          {subtitle && <p className="m-0 truncate text-[11.5px] text-muted-foreground">{subtitle}</p>}
        </div>
        {actions}
      </header>
      <div className="p-3.5">{children}</div>
    </section>
  );
}

export function NeedsModel() {
  return <p className="m-0 text-[12px] text-muted-foreground">Tell the wizard what you want to classify first; this opens once the model exists.</p>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "good" | "bad" }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-surface/40 px-3 py-2">
      <div className="text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">{label}</div>
      <div className={cn("mt-0.5 text-xl font-semibold tabular-nums", tone === "good" && "text-emerald-600 dark:text-emerald-400", tone === "bad" && "text-red-600 dark:text-red-400")}>{value}</div>
      {hint && <div className="truncate text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

export const pct = (v: number | null | undefined, digits = 0) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);
