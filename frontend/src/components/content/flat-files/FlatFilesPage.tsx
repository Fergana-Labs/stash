"use client";

// Experimental full-screen VFS: no tree, no folders — one reverse-chron table
// of everything in the stash. The search input is the topbar's search bar
// (topbar.tsx renders it on /files and writes to the shared store); this page
// renders the filtered results. Arrows move, Enter opens.

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/components/content/files-overview/build";
import { useFilesSearch } from "./search-store";
import { FlatItemIcon, filterItems, useFlatItems, type FlatItem, type FlatKind } from "./useFlatItems";

const PAGE_SIZE = 100;

const KINDS: { kind: FlatKind; label: string }[] = [
  { kind: "page", label: "Pages" },
  { kind: "file", label: "Files" },
  { kind: "table", label: "Tables" },
  { kind: "session", label: "Sessions" },
  { kind: "skill", label: "Skills" },
];

// One shared grid so the header and every row line up as table columns.
const COLUMNS =
  "grid grid-cols-[minmax(0,3fr)_80px_minmax(0,1.2fr)_minmax(0,1fr)_80px] items-center gap-x-4";

const KIND_NAME: Record<FlatKind, string> = {
  page: "Page",
  file: "File",
  table: "Table",
  session: "Session",
  skill: "Skill",
};

type SortKey = "name" | "type" | "folder" | "agent" | "modified";
type Sort = { key: SortKey; dir: "asc" | "desc" };

// Modified-desc is what the list already arrives in, and doubles as "default":
// while searching under the default sort, relevance ranking wins instead.
const DEFAULT_SORT: Sort = { key: "modified", dir: "desc" };

function compareBy(key: SortKey, a: FlatItem, b: FlatItem): number {
  if (key === "modified") return +new Date(a.updatedAt) - +new Date(b.updatedAt);
  if (key === "name") return a.name.localeCompare(b.name);
  if (key === "type") return KIND_NAME[a.kind].localeCompare(KIND_NAME[b.kind]);
  if (key === "folder") return (a.context ?? "").localeCompare(b.context ?? "");
  return (a.agent ?? "").localeCompare(b.agent ?? "");
}

function HeaderCell({
  label,
  sortKey,
  sort,
  onSort,
  right,
}: {
  label: string;
  sortKey: SortKey;
  sort: Sort;
  onSort: (key: SortKey) => void;
  right?: boolean;
}) {
  const active = sort.key === sortKey;
  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className={cn(
        "flex items-center gap-1 font-mono text-[10.5px] uppercase tracking-wide",
        right && "justify-end",
        active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
      <span className={cn("w-2", !active && "invisible")}>{sort.dir === "asc" ? "↑" : "↓"}</span>
    </button>
  );
}

function Chip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-2.5 py-0.5 text-[12px]",
        active
          ? "border-brand-500/40 bg-brand-500/10 text-brand-700"
          : "border-border text-muted-foreground hover:bg-raised",
      )}
    >
      {label}
    </button>
  );
}

export default function FlatFilesPage() {
  const router = useRouter();
  const { items, loaded, error } = useFlatItems();
  const query = useFilesSearch((s) => s.query);
  const [kind, setKind] = useState<FlatKind | "all">("all");
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [activeIdx, setActiveIdx] = useState(0);
  const [limit, setLimit] = useState(PAGE_SIZE);
  // Only keyboard moves scroll the active row into view; mouse and initial
  // renders must not yank the page around.
  const keyed = useRef(false);

  const ofKind = useMemo(
    () => (kind === "all" ? items : items.filter((i) => i.kind === kind)),
    [items, kind],
  );
  const searching = query.trim().length > 0;
  const matches = useMemo(() => {
    const filtered = filterItems(ofKind, query);
    const isDefault = sort.key === DEFAULT_SORT.key && sort.dir === DEFAULT_SORT.dir;
    // Relevance order survives only under the default sort; an explicit sort
    // is a stronger statement than the ranker.
    if (searching && isDefault) return filtered;
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => sign * compareBy(sort.key, a, b));
  }, [ofKind, query, searching, sort]);
  const visible = matches.slice(0, limit);

  function onSort(key: SortKey) {
    setActiveIdx(0);
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "modified" ? "desc" : "asc" },
    );
  }

  // The topbar owns the input; leaving the page clears the shared query so a
  // return visit starts with the full list.
  useEffect(() => () => useFilesSearch.getState().setQuery(""), []);

  useEffect(() => {
    setActiveIdx(0);
    setLimit(PAGE_SIZE);
  }, [query]);

  // Keyboard driving happens at window level: focus sits in the topbar input
  // while the results live here.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!searching || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        keyed.current = true;
        setActiveIdx((i) => Math.min(i + 1, visible.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        keyed.current = true;
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && visible[activeIdx]) {
        router.push(visible[activeIdx].href);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [searching, visible, activeIdx, router]);

  if (error) {
    return <div className="p-6 font-mono text-[12px] text-error">✗ couldn&apos;t read the stash: {error}</div>;
  }

  return (
    <div className="h-full overflow-y-auto bg-base">
      <div className="mx-auto w-full max-w-5xl px-6 py-8">
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip
            active={kind === "all"}
            label={`All ${items.length}`}
            onClick={() => { setKind("all"); setActiveIdx(0); }}
          />
          {KINDS.map(({ kind: k, label }) => {
            const count = items.filter((i) => i.kind === k).length;
            if (count === 0) return null;
            return (
              <Chip
                key={k}
                active={kind === k}
                label={`${label} ${count}`}
                onClick={() => { setKind(k); setActiveIdx(0); }}
              />
            );
          })}
        </div>

        <div className="mt-4">
          {!loaded && (
            <div className="space-y-3 py-2">
              {Array.from({ length: 10 }, (_, i) => (
                <Skeleton key={i} className="h-5" style={{ width: `${55 + (i % 4) * 12}%` }} />
              ))}
            </div>
          )}

          {loaded && matches.length === 0 && (
            <div className="py-8 text-center font-mono text-[12px] text-muted-foreground">
              {searching ? <>no matches for &ldquo;{query.trim()}&rdquo;</> : "nothing here yet"}
            </div>
          )}

          {loaded && matches.length > 0 && (
            <div className={cn("border-b border-border px-3 pb-1.5", COLUMNS)}>
              <HeaderCell label="Name" sortKey="name" sort={sort} onSort={onSort} />
              <HeaderCell label="Type" sortKey="type" sort={sort} onSort={onSort} />
              <HeaderCell label="Folder" sortKey="folder" sort={sort} onSort={onSort} />
              <HeaderCell label="Agent" sortKey="agent" sort={sort} onSort={onSort} />
              <HeaderCell label="Modified" sortKey="modified" sort={sort} onSort={onSort} right />
            </div>
          )}

          {visible.map((item, idx) => (
            <Link
              key={item.key}
              href={item.href}
              ref={
                searching && idx === activeIdx
                  ? (el) => {
                      if (el && keyed.current) {
                        keyed.current = false;
                        el.scrollIntoView({ block: "nearest" });
                      }
                    }
                  : undefined
              }
              onMouseMove={() => { if (searching) setActiveIdx(idx); }}
              className={cn(
                "rounded-md px-3 py-2",
                COLUMNS,
                searching && idx === activeIdx ? "bg-brand-500/10" : "hover:bg-raised",
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <FlatItemIcon kind={item.kind} />
                <span className="min-w-0 truncate text-[13.5px] text-foreground">{item.name}</span>
                {item.annotation && (
                  <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">{item.annotation}</span>
                )}
              </span>
              <span className="truncate text-[12px] text-muted-foreground">{KIND_NAME[item.kind]}</span>
              <span className="truncate text-[12px] text-muted-foreground">{item.context ?? "—"}</span>
              <span className="truncate font-mono text-[11px] text-muted-foreground">{item.agent ?? "—"}</span>
              <span className="text-right font-mono text-[11px] text-muted-foreground">{timeAgo(item.updatedAt)}</span>
            </Link>
          ))}

          {matches.length > visible.length && (
            <button
              type="button"
              onClick={() => setLimit((l) => l + 500)}
              className="mt-1 flex w-full items-center gap-1 rounded-md px-3 py-1.5 text-left font-mono text-[11.5px] text-dim hover:bg-raised hover:text-brand-700"
            >
              … +{matches.length - visible.length} more
            </button>
          )}

          {searching && (
            <Link
              href={`/search?q=${encodeURIComponent(query.trim())}`}
              className="mt-2 flex items-center gap-1 rounded-md px-3 py-1.5 font-mono text-[11.5px] text-dim hover:bg-raised hover:text-brand-700"
            >
              search connected sources too <ArrowUpRight className="h-3 w-3" />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
