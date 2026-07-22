"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type RefObject } from "react";
import { getSidebar, listAllTables, semanticSearchPages, type Sidebar } from "../lib/api";
import type { TableWithOwner } from "../lib/types";
import type { SearchScope } from "@/lib/searchScope";
import { routes } from "@/lib/workspace-routes";
import { useEscapeKey } from "../hooks/useEscapeKey";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLDivElement | null>;
  searchScope: SearchScope | null;
}

interface Result {
  kind: "search" | "page" | "session" | "folder" | "file" | "table";
  label: string;
  href: string;
  detail?: string;
}

export default function CommandPalette({
  open,
  onClose,
  anchorRef,
  searchScope,
}: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [spine, setSpine] = useState<Sidebar | null>(null);
  const [tables, setTables] = useState<TableWithOwner[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [selected, setSelected] = useState(0);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEscapeKey(open, onClose);

  useEffect(() => {
    if (open) setAnchorRect(anchorRef.current?.getBoundingClientRect() ?? null);
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setQuery("");
    setResults([]);
    setSelected(0);
    setTables([]);
    inputRef.current?.focus();
    getSidebar()
      .then((nextSpine) => {
        if (!cancelled) setSpine(nextSpine);
      })
      .catch(() => {});
    listAllTables()
      .then((data) => {
        if (!cancelled) setTables(data.tables);
      })
      .catch(() => {
        if (!cancelled) setTables([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setResults([]);
      setSelected(0);
      return;
    }
    const fullPageSearch = fullPageSearchResult(searchScope, query);
    if (!query.trim()) {
      setResults([fullPageSearch]);
      setSelected(0);
      return;
    }
    const q = query.toLowerCase();

    // Local spine fuzzy match (instant)
    const local: Result[] = [fullPageSearch];
    if (spine) {
      const filesTree = spine.files;
      filesTree.pages.forEach((p) => {
        if (p.name.toLowerCase().includes(q))
          local.push({
            kind: "page",
            label: p.name.replace(/\.md$/, ""),
            href: routes.page(p.id),
            detail: p.content_type === "html" ? "HTML page" : "Page",
          });
      });
      spine.sessions.forEach((s) => {
        if (s.session_id.toLowerCase().includes(q))
          local.push({
            kind: "session",
            label: `#${s.session_id}`,
            href: routes.session(s.session_id),
            detail: s.agent_name,
          });
      });
      filesTree.folders.forEach((f) => {
        if (f.name.toLowerCase().includes(q))
          local.push({
            kind: "folder",
            label: f.name,
            href: routes.folder(f.id),
            detail: `${f.page_count} pages · ${f.file_count} files`,
          });
      });
      filesTree.files.forEach((f) => {
        if (f.name.toLowerCase().includes(q))
          local.push({
            kind: "file",
            label: f.name,
            href: f.linked_table_id
              ? routes.table(f.linked_table_id)
              : routes.file(f.id),
            detail: f.content_type,
          });
      });
    }
    tables.forEach((table) => {
      if (!tableMatchesQuery(table, q)) return;
      local.push({
        kind: "table",
        label: table.name,
        href: tableHref(table),
        detail: tableDetail(table),
      });
    });
    setResults(local.slice(0, 12));
    setSelected(0);

    // Remote debounce (250ms): semantic page search
    const timer = setTimeout(async () => {
      try {
        const pages = await semanticSearchPages(query, 6);
        const remote: Result[] = pages.map((p) => ({
          kind: "page" as const,
          label: p.name.replace(/\.md$/, ""),
          href: routes.page(p.id),
          detail: "Page",
        }));
        setResults((prev) => {
          const ids = new Set(prev.map((r) => r.href));
          return [...prev, ...remote.filter((r) => !ids.has(r.href))].slice(0, 16);
        });
      } catch {
        // search not available
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query, open, spine, tables, searchScope]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(s + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(s - 1, 0));
      } else if (e.key === "Enter" && results[selected]) {
        router.push(results[selected].href);
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, results, selected, onClose, router]);

  if (!open) return null;

  const kindIcon: Record<string, string> = {
    search: "⌕",
    page: "📄",
    session: "#",
    file: "📁",
    table: "T",
  };

  return (
    <div className="fixed inset-0 z-[60] cursor-pointer bg-transparent" onClick={onClose}>
      <div
        className="absolute flex max-h-[calc(100vh-1rem)] flex-col overflow-hidden rounded-[20px] border border-border bg-base shadow-[0_8px_30px_-8px_rgba(0,0,0,0.18)] ring-1 ring-black/[0.04]"
        style={{
          left: anchorRect?.left,
          top: anchorRect?.top,
          width: anchorRect?.width,
        }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Search"
      >
        <div className="flex items-center gap-3 px-4 py-2.5">
          <svg className="h-4 w-4 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search Skill or jump to a page, session, file, or table..."
            className="min-w-0 flex-1 bg-transparent text-[14px] text-foreground placeholder:text-muted-foreground focus:outline-none"
            autoFocus
          />
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-surface hover:text-foreground"
            aria-label="Close search"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>

        {results.length > 0 ? (
          <div className="max-h-[calc(100vh-5.5rem)] overflow-y-auto p-2">
            {results.map((r, i) => (
              <Link
                key={r.href + i}
                href={r.href}
                onClick={onClose}
                className={
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] transition-colors " +
                  (i === selected ? "bg-[var(--color-brand-50)] text-foreground" : "text-dim hover:bg-raised")
                }
              >
                <span className="w-5 text-center text-[14px] text-muted-foreground">
                  {kindIcon[r.kind] || "·"}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{r.label}</div>
                  {r.detail && <div className="truncate text-[11px] text-muted-foreground">{r.detail}</div>}
                </div>
                {r.kind !== "search" && <span className="rounded bg-surface px-1 py-0 text-[9px] uppercase tracking-wide text-muted-foreground ring-1 ring-border">
                  {r.kind}
                </span>}
              </Link>
            ))}
          </div>
        ) : query ? (
          <div className="px-4 py-6 text-center text-[13px] text-muted-foreground">
            No results for &quot;{query}&quot;
          </div>
        ) : (
          <div className="px-4 py-6 text-center text-[13px] text-muted-foreground">
            Start typing to search this skill...
          </div>
        )}
      </div>
    </div>
  );
}

function fullPageSearchResult(scope: SearchScope | null, query: string): Result {
  const params = new URLSearchParams(scope?.params);

  const q = query.trim();
  if (q) params.set("q", q);

  const label = scope?.label ?? "Skill";
  const hrefParams = params.toString();

  return {
    kind: "search",
    label: q ? `Search ${label} for "${q}"` : `Search ${label}`,
    href: hrefParams ? `/search?${hrefParams}` : "/search",
    detail: scope?.detail ?? "Search everything",
  };
}

function tableMatchesQuery(table: TableWithOwner, query: string): boolean {
  const columns = table.columns.map((column) => column.name).join(" ");
  return [table.name, table.description, columns].some((value) =>
    value.toLowerCase().includes(query)
  );
}

function tableHref(table: TableWithOwner): string {
  return routes.table(table.id);
}

function tableDetail(table: TableWithOwner): string {
  const parts = ["Table"];
  if (typeof table.row_count === "number") {
    parts.push(`${table.row_count} row${table.row_count === 1 ? "" : "s"}`);
  }
  return parts.join(" · ");
}
