"use client";

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import DownloadMenu, { type DownloadOption } from "../DownloadMenu";
import EditableTitle from "./EditableTitle";

export type FileViewerSaveStatus = "saved" | "dirty" | "saving";

interface BackLink {
  label: string;
  href: string;
}

interface Breadcrumb {
  label: string;
  href: string;
}

interface Tag {
  label: string;
  tone?: "brand" | "muted";
}

interface FileViewerHeaderProps {
  /** Big rounded glyph in the identity strip. */
  icon: ReactNode;
  /** Tint applied to the icon container's `color`. */
  iconColor?: string;
  /** The displayed title. */
  title: string;
  /** When set + !readOnly, the title is editable. Returns the canonical title. */
  onRenameTitle?: (next: string) => Promise<string>;
  /** Read-only mode hides rename + write affordances and shows a chip. */
  readOnly?: boolean;
  /** Chip text in read-only mode. Defaults to "read-only". */
  readOnlyLabel?: string;
  /** Back link rendered above the title (e.g. "← Demo Skill"). */
  backLink?: BackLink;
  /** Ancestor trail rendered before the title in the compact bar
   *  (e.g. Files / Research / — the title itself is the last crumb). */
  breadcrumbs?: Breadcrumb[];
  /** Small label chips before the meta items. */
  tags?: Tag[];
  /**
   * Free-form meta items rendered before the spacer + download menu. Use
   * short strings like "Last edited Jun 5" or "12 KB".
   */
  meta?: ReactNode[];
  /** "saved" | "dirty" | "saving" — colored save-status text. Hidden in read-only mode. */
  saveStatus?: FileViewerSaveStatus | null;
  /** Right-aligned download menu options. Omit to hide. */
  downloadOptions?: DownloadOption[];
  /** Anything that should sit between the save-status and the download menu. */
  rightExtras?: ReactNode;
}

const SAVE_LABEL = { saving: "Saving…", dirty: "Unsaved", saved: "Saved" } as const;
const SAVE_TONE = { saving: "text-amber-500", dirty: "text-amber-600", saved: "text-emerald-600" } as const;

/**
 * Standard header for the file/page/table viewers: one clean single-row bar —
 * icon, breadcrumbs, title (editable or read-only), tags, meta, save status,
 * and a Download menu. The page viewer (`/p/[id]`), the file viewer
 * (`/f/[id]`), and the table viewer (`/tables/[id]`) all use this so the
 * entry visual for "you are looking at a thing" is the same shape across kinds.
 */
export default function FileViewerHeader({
  icon,
  iconColor,
  title,
  onRenameTitle,
  readOnly,
  readOnlyLabel = "read-only",
  backLink,
  breadcrumbs,
  tags,
  meta,
  saveStatus,
  downloadOptions,
  rightExtras,
}: FileViewerHeaderProps) {
  const iconStyle: CSSProperties = {
    color: iconColor ?? "var(--text-muted)",
  };

  return (
    <div className="flex h-11 shrink-0 items-center gap-2.5 border-b border-border bg-base px-4">
      <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-border bg-base text-[14px]" style={iconStyle}>
        {icon}
      </span>
      {backLink && (
        <span className="hidden shrink-0 items-center gap-2.5 text-[12.5px] text-muted-foreground sm:inline-flex">
          <Link href={backLink.href} className="max-w-[160px] truncate hover:text-foreground">&larr; {backLink.label}</Link>
          <span className="text-muted-foreground/50">/</span>
        </span>
      )}
      {breadcrumbs?.map((crumb) => (
        <span key={crumb.href} className="hidden shrink-0 items-center gap-2.5 text-[12.5px] text-muted-foreground sm:inline-flex">
          <Link href={crumb.href} className="max-w-[160px] truncate hover:text-foreground">{crumb.label}</Link>
          <span className="text-muted-foreground/50">/</span>
        </span>
      ))}
      <span className="min-w-0 shrink truncate text-[13.5px] font-semibold text-foreground">
        {readOnly || !onRenameTitle ? title : <EditableTitle value={title} onSave={onRenameTitle} />}
      </span>
      {tags?.map((tag, i) => (
        <span key={`${tag.label}-${i}`} className={"tag shrink-0 " + (tag.tone === "brand" ? "tag-brand" : "tag-muted")}>{tag.label}</span>
      ))}
      <span className="flex min-w-0 items-center gap-2 truncate text-[12px] text-muted-foreground">
        {meta?.map((item, i) => <span key={i} className="shrink-0">{item}</span>)}
        {!readOnly && saveStatus && <span className={SAVE_TONE[saveStatus]}>{SAVE_LABEL[saveStatus]}</span>}
        {readOnly && <span className="rounded-md bg-surface px-2 py-0.5 text-[10.5px] font-medium uppercase tracking-wide">{readOnlyLabel}</span>}
      </span>
      <span className="flex-1" />
      <div className="flex shrink-0 items-center gap-2">
        {rightExtras}
        {downloadOptions && downloadOptions.length > 0 && <DownloadMenu options={downloadOptions} />}
      </div>
    </div>
  );
}
