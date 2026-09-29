"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Loader2, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RmJobStatus } from "@/lib/types";

const TABS = [
  { href: "/reward-models", label: "Traces", match: (p: string) => p === "/reward-models" || p.startsWith("/reward-models/traces") },
  { href: "/reward-models/models", label: "Reward models", match: (p: string) => p.startsWith("/reward-models/models") },
  { href: "/reward-models/gepa", label: "Skills", match: (p: string) => p.startsWith("/reward-models/gepa") },
];

/** Page frame shared by the list pages: title, description, the section tabs, and an actions slot. */
export function RmPage({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();
  // h-full makes this the page's scroll container, so sticky bars inside it (the trace selection bar) stick.
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-10 pt-7 pb-16">
        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0">
            <h1 className="m-0 font-display text-[22px] font-semibold tracking-tight text-foreground">{title}</h1>
            <p className="m-0 mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">{description}</p>
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
        <nav className="mt-5 mb-6 flex gap-5 border-b border-border">
          {TABS.map((tab) => {
            const active = tab.match(pathname);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={cn(
                  "-mb-px border-b-2 pb-2 text-[13px] font-medium transition-colors",
                  active
                    ? "border-brand-500 text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
        {children}
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<RmJobStatus, string> = {
  queued: "tag-muted",
  running: "tag-warning",
  succeeded: "tag-success",
  failed: "bg-red-500/10 text-red-600",
};

export function StatusBadge({ status }: { status: RmJobStatus }) {
  const active = status === "queued" || status === "running";
  return (
    <span className={cn("tag", STATUS_STYLE[status])}>
      {active && <Loader2 className="h-3 w-3 animate-spin" />}
      {status}
    </span>
  );
}

export function isActiveJob(status: RmJobStatus): boolean {
  return status === "queued" || status === "running";
}

/** A + or − toggle. `count` is how many annotators gave this rating; `mine` is whether the viewer did. */
export function RatingButton({
  rating,
  count,
  mine,
  pending,
  onClick,
  size = "sm",
}: {
  rating: 1 | -1;
  count: number;
  mine: boolean;
  pending: boolean;
  onClick: () => void;
  size?: "sm" | "md";
}) {
  const positive = rating === 1;
  const Icon = positive ? Plus : Minus;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending}
      aria-pressed={mine}
      aria-label={positive ? "Rate +" : "Rate −"}
      title={positive ? "Good (+)" : "Bad (−)"}
      className={cn(
        "inline-flex cursor-pointer items-center gap-1 rounded-md border font-mono tabular-nums transition-colors disabled:cursor-wait disabled:opacity-60",
        size === "sm" ? "h-6 px-1.5 text-[11px]" : "h-7 px-2 text-[12px]",
        mine
          ? positive
            ? "border-green-600/40 bg-green-600/12 text-green-700 dark:text-green-400"
            : "border-red-500/40 bg-red-500/12 text-red-600 dark:text-red-400"
          : "border-border bg-background text-muted-foreground hover:border-foreground/20 hover:text-foreground",
      )}
    >
      {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Icon className="h-3 w-3" strokeWidth={2.5} />}
      {count > 0 && <span>{count}</span>}
    </button>
  );
}

export function RatingPill({ rating }: { rating: 1 | -1 }) {
  return rating === 1 ? (
    <span className="tag tag-success">+ good</span>
  ) : (
    <span className="tag bg-red-500/10 text-red-600">− bad</span>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface/40 px-6 py-10 text-center">
      <p className="m-0 text-[13.5px] font-medium text-foreground">{title}</p>
      {children && <div className="mt-1.5 text-[12.5px] text-muted-foreground">{children}</div>}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-dim">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11.5px] leading-snug text-muted-foreground">{hint}</span>}
    </label>
  );
}

/** Title for a skill run with no skill name yet: it is still being written, or the run failed. */
export function pendingSkillTitle(status: RmJobStatus): string {
  return status === "failed" ? "Skill creation failed" : "Writing skill…";
}
