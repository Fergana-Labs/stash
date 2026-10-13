import type { ReactNode } from "react";
import type { Item } from "@/lib/intuition-api";
import styles from "./eval-ui.module.css";

export const evalSurfaceClass = styles.surface;
export const evalInputClass = "w-full resize-none rounded border border-border bg-background px-2.5 py-2 text-[12px] leading-5 text-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/10 disabled:opacity-50";

export function EvalPageFrame({ title, description, actions, children }: { title?: string; description?: string; actions?: ReactNode; children: ReactNode }) {
  return <div className={`${styles.surface} scroll-thin h-full overflow-y-auto bg-background`}><div className="px-6 pt-5 pb-10">
    {title && <header className="mb-5 flex items-start justify-between gap-4"><div><h1 className="text-lg font-semibold tracking-tight">{title}</h1>{description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}</div>{actions}</header>}
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
