import type { ReactNode } from "react";
import type { Item } from "@/lib/intuition-api";
import { Minus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import styles from "./eval-ui.module.css";

export const evalSurfaceClass = styles.surface;
export const evalInputClass = "w-full resize-none rounded border border-border bg-background px-2.5 py-2 text-[12px] leading-5 text-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/10 disabled:opacity-50";

export function EvalPageFrame({ title, description, actions, children }: { title?: string; description?: string; actions?: ReactNode; children: ReactNode }) {
  return <div className={`${styles.surface} scroll-thin h-full overflow-y-auto bg-background`}><div className="px-5 pt-4 pb-8">
    {title && <header className="mb-4 flex items-start justify-between gap-4"><div><h1 className="text-[16px] font-semibold tracking-tight">{title}</h1>{description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}</div>{actions}</header>}
    {children}
  </div></div>;
}

export function examplePreview(item: Item): string {
  if (typeof item === "string") return item;
  for (const key of ["reply", "output", "content", "title", "name"]) {
    if (typeof item[key] === "string") return item[key];
  }
  return JSON.stringify(item);
}


export function InlinePanel({ title, onClose, children, disabled = false, className }: { title: string; onClose: () => void; children: ReactNode; disabled?: boolean; className?: string }) {
  return <section aria-label={title} className={cn("grid gap-3 rounded border border-border bg-surface/30 p-4 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-top-2 duration-150", className)} onKeyDown={(event) => { if (event.key === "Escape" && !disabled) { event.stopPropagation(); onClose(); } }}>
    <header className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">{title}</h3><Button variant="ghost" size="icon-xs" aria-label={`Collapse ${title}`} title="Collapse" disabled={disabled} onClick={onClose}><Minus /></Button></header>
    {children}
  </section>;
}
