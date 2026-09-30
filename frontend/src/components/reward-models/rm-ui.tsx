"use client";

import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RmJobStatus } from "@/lib/types";

/** Page frame shared by the list pages: title, description, and an actions slot. */
export function RmPage({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  // h-full makes this the page's scroll container, so sticky bars inside it (the trace selection bar) stick.
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-10 pt-7 pb-16">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0">
            <h1 className="m-0 font-display text-[22px] font-semibold tracking-tight text-foreground">{title}</h1>
            {description && <p className="m-0 mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
        {children}
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<RmJobStatus, string> = {
  queued: "tag-muted",
  running: "tag-warning",
  succeeded: "",
  failed: "bg-red-500/10 text-red-600",
};

export function StatusBadge({ status }: { status: RmJobStatus }) {
  if (status === "succeeded") return null;
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
