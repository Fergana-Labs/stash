"use client";

import { PinIcon } from "../../StashIcons";
import type { GridItem } from "./FolderItemGrid";
import { KindIcon, tintFor, typeFor } from "./ItemsList";

interface Props {
  pinned: GridItem[];
  recent: GridItem[];
  onOpen: (item: GridItem) => void;
  isPinned: (item: GridItem) => boolean;
  onTogglePin: (item: GridItem) => void;
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
}: {
  item: GridItem;
  pinned: boolean;
  onOpen: (item: GridItem) => void;
  onTogglePin: (item: GridItem) => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(item)}
      onKeyDown={(e) => {
        if (e.key === "Enter") onOpen(item);
      }}
      className="group/qa relative flex w-[180px] cursor-pointer items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2.5 text-left transition hover:border-[var(--color-brand-300)] hover:bg-raised"
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
