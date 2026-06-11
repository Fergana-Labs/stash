"use client";

import { useState, type DragEvent } from "react";
import { shouldOpenInNewTab, type NavigateOptions } from "../../../lib/linkNavigation";
import { PinIcon } from "../../SkillIcons";
import type { FBDragPayload } from "./WorkspaceFileBrowser";
import { handleFolderDrop, isFbDrag, startItemDrag } from "./ItemsList";
import { KindIcon, tintFor, typeFor, type GridItem } from "./kind";

interface Props {
  pinned: GridItem[];
  recent: GridItem[];
  onOpen: (item: GridItem, options?: NavigateOptions) => void;
  isPinned: (item: GridItem) => boolean;
  onTogglePin: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onReparentMany: (payloads: FBDragPayload[], targetFolderId: string | null) => Promise<void>;
}

// Quick-access strip above the file list: pinned items the user chose, plus a
// recents row sorted by last-modified. Both render as compact cards that open
// the item; the pin toggle is always visible on pinned cards and hover-only on
// recents so the row stays calm until you reach for it.
export default function QuickAccess({
  pinned,
  recent,
  onOpen,
  isPinned,
  onTogglePin,
  onReparent,
  onReparentMany,
}: Props) {
  return (
    <div className="mt-5 space-y-4">
      {pinned.length > 0 && (
        <Section title="Pinned">
          {pinned.map((item) => (
            <Card
              key={`pin-${item.kind}-${item.id}`}
              item={item}
              pinned
              onOpen={onOpen}
              onTogglePin={onTogglePin}
              onReparent={onReparent}
              onReparentMany={onReparentMany}
            />
          ))}
        </Section>
      )}
      {recent.length > 0 && (
        <Section title="Recent">
          {recent.map((item) => (
            <Card
              key={`recent-${item.kind}-${item.id}`}
              item={item}
              pinned={isPinned(item)}
              onOpen={onOpen}
              onTogglePin={onTogglePin}
              onReparent={onReparent}
              onReparentMany={onReparentMany}
            />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="m-0 mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
        {title}
      </h2>
      <div className="flex flex-wrap gap-2.5">{children}</div>
    </section>
  );
}

function Card({
  item,
  pinned,
  onOpen,
  onTogglePin,
  onReparent,
  onReparentMany,
}: {
  item: GridItem;
  pinned: boolean;
  onOpen: (item: GridItem, options?: NavigateOptions) => void;
  onTogglePin: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onReparentMany: (payloads: FBDragPayload[], targetFolderId: string | null) => Promise<void>;
}) {
  const [over, setOver] = useState(false);
  const isFolder = item.kind === "folder";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={(e) => onOpen(item, { newTab: shouldOpenInNewTab(e) })}
      onAuxClick={(e) => {
        if (shouldOpenInNewTab(e)) onOpen(item, { newTab: true });
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") onOpen(item);
      }}
      draggable={item.movable !== false}
      onDragStart={(e: DragEvent<HTMLDivElement>) => startItemDrag(e, item, false, [])}
      onDragOver={(e) => {
        if (!isFolder) return;
        if (!isFbDrag(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        if (!isFolder) return;
        setOver(false);
        e.preventDefault();
        handleFolderDrop(e, item.id, onReparent, onReparentMany);
      }}
      className={
        "group/qa relative flex w-[180px] cursor-pointer items-center gap-2.5 rounded-lg border bg-surface px-3 py-2.5 text-left transition hover:border-[var(--color-brand-300)] hover:bg-raised " +
        (over ? "border-[var(--color-brand-300)] ring-1 ring-inset ring-[var(--color-brand-300)]" : "border-border")
      }
    >
      <span className={"flex h-5 w-5 shrink-0 items-center justify-center " + tintFor(item)}>
        <KindIcon kind={item.kind} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium text-foreground">
          {item.name}
        </span>
        <span className="block truncate text-[10.5px] text-muted">{typeFor(item)}</span>
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onTogglePin(item);
        }}
        className={
          "flex h-5 w-5 shrink-0 items-center justify-center rounded text-[14px] transition " +
          (pinned
            ? "text-[var(--color-brand-600)] hover:text-[var(--color-brand-700)]"
            : "text-muted opacity-0 hover:text-foreground focus-visible:opacity-100 group-hover/qa:opacity-100")
        }
        title={pinned ? "Unpin" : "Pin"}
        aria-label={pinned ? "Unpin" : "Pin"}
        aria-pressed={pinned}
      >
        <PinIcon />
      </button>
    </div>
  );
}
