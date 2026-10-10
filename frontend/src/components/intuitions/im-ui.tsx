"use client";

import { createContext, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { Example, ExampleSource, ModelDetail, Version } from "@/lib/intuition-api";

export { inputClass } from "@/components/workbench/workbench-ui";

export const TABS = [
  { id: "playground", label: "Playground" },
  { id: "inbox", label: "Inbox" },
  { id: "examples", label: "Examples" },
  { id: "rubric", label: "Rubric" },
  { id: "train", label: "Train" },
  { id: "versions", label: "Versions" },
] as const;
export type TabId = (typeof TABS)[number]["id"];

export function isTabId(value: string | null): value is TabId {
  return TABS.some((t) => t.id === value);
}

/** Everything the detail tabs share: the model, its examples, and navigation. */
export interface IntuitionCtx {
  id: string;
  detail: ModelDetail;
  /** Draft if there is one, else active. Edits always land on the draft. */
  version: Version | null;
  apply: (detail: ModelDetail) => void;
  reload: () => Promise<void>;
  examples: Example[] | null;
  examplesError: string | null;
  setExamples: Dispatch<SetStateAction<Example[] | null>>;
  reloadExamples: () => Promise<void>;
  goTo: (tab: TabId, params?: Record<string, string>) => void;
}

const Ctx = createContext<IntuitionCtx | null>(null);
export const IntuitionProvider = Ctx.Provider;

export function useIntuition(): IntuitionCtx {
  const value = useContext(Ctx);
  if (!value) throw new Error("useIntuition must be used inside IntuitionProvider");
  return value;
}

/** A bordered section with an optional header row. */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-border bg-background", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border-subtle px-4 py-2.5">
          <div className="min-w-0">
            {title && <h2 className="m-0 text-[13px] font-semibold text-foreground">{title}</h2>}
            {description && <p className="m-0 mt-0.5 text-[12px] leading-snug text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-1.5">{actions}</div>}
        </header>
      )}
      {children !== undefined && <div className="px-4 py-3">{children}</div>}
    </section>
  );
}

export function Metric({ label, value, hint, emphasis }: { label: string; value: string; hint?: string; emphasis?: boolean }) {
  return (
    <div className="bg-surface/60 px-3 py-2">
      <dt className="text-[10.5px] tracking-wide text-muted-foreground uppercase">{label}</dt>
      <dd className={cn("m-0 mt-0.5 font-mono tabular-nums text-foreground", emphasis ? "text-[16px] font-semibold" : "text-[13px]")}>{value}</dd>
      {hint && <div className="text-[10.5px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function MetricGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <dl className={cn("m-0 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle sm:grid-cols-4", className)}>
      {children}
    </dl>
  );
}

const SOURCE_CLASS: Record<ExampleSource, string> = {
  human: "tag-human",
  agent: "tag-agent",
  generated: "tag-warning",
  production: "tag-success",
};

export function SourceTag({ source }: { source: ExampleSource }) {
  return <span className={cn("tag", SOURCE_CLASS[source])}>{source}</span>;
}

export function LabelTag({ label, tone = "muted", className }: { label: string; tone?: "muted" | "brand" | "success" | "danger"; className?: string }) {
  return (
    <span
      className={cn(
        "tag normal-case",
        tone === "muted" && "tag-muted",
        tone === "brand" && "tag-brand",
        tone === "success" && "tag-success",
        tone === "danger" && "bg-red-500/10 text-red-600 dark:text-red-400",
        className,
      )}
    >
      {label}
    </span>
  );
}

/** Horizontal 0–1 bar. */
export function Bar({ value, tone = "muted", className }: { value: number; tone?: "muted" | "brand"; className?: string }) {
  const width = `${Math.max(0, Math.min(1, value)) * 100}%`;
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-raised", className)}>
      <div className={cn("h-full rounded-full", tone === "brand" ? "bg-brand-500" : "bg-foreground/35")} style={{ width }} />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-3.5 w-3.5 animate-spin", className)} aria-hidden="true" />;
}

export function LoadError({ message, onRetry, what }: { message: string; onRetry?: () => void; what: string }) {
  return (
    <div role="alert" className="py-6 text-sm">
      <p className="m-0 font-medium">Couldn’t load {what}.</p>
      <p className="m-0 mt-1 text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Inline callout for state the user should act on. */
export function Callout({ tone = "info", children, action }: { tone?: "info" | "warning" | "danger"; children: ReactNode; action?: ReactNode }) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-[12.5px]",
        tone === "info" && "border-border bg-surface/60 text-dim",
        tone === "warning" && "border-yellow-500/30 bg-yellow-500/8 text-yellow-900 dark:text-yellow-200",
        tone === "danger" && "border-red-500/25 bg-red-500/5 text-red-700 dark:text-red-400",
      )}
    >
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

/** Confirmation dialog whose confirm action may be async; stays open while it runs. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: () => Promise<boolean | void>;
}) {
  const [busy, setBusy] = useState(false);
  async function confirm() {
    setBusy(true);
    try {
      const keepOpen = (await onConfirm()) === false;
      if (!keepOpen) onOpenChange(false);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription asChild>
            <div className="text-[13px] leading-relaxed">{description}</div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={() => void confirm()} disabled={busy}>
            {busy && <Spinner />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Segmented control for a small set of options. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  size = "sm",
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: ReactNode }[];
  ariaLabel: string;
  size?: "xs" | "sm";
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex rounded-md border border-border bg-surface/50 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-[5px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
            size === "xs" ? "px-2 py-0.5 text-[11.5px]" : "px-2.5 py-1 text-[12px]",
            value === o.value ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
