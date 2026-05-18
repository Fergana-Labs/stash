"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { semanticSearchPages, type WorkspaceSidebar } from "../lib/api";
import {
  getCachedWorkspaceSidebar,
  readCachedWorkspaceSidebar,
} from "../lib/stashNavigationCache";
import type { SearchScope } from "./AppShell";
import { useEscapeKey } from "../hooks/useEscapeKey";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string | null;
  workspaceName?: string | null;
  searchScope: SearchScope | null;
}

interface Result {
  kind: "search" | "page" | "session" | "folder" | "file";
  label: string;
  href: string;
  detail?: string;
}

export default function CommandPalette({
  open,
  onClose,
  workspaceId,
  workspaceName,
  searchScope,
}: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [spine, setSpine] = useState<WorkspaceSidebar | null>(() =>
    workspaceId ? readCachedWorkspaceSidebar(workspaceId) : null
  );
  const [results, setResults] = useState<Result[]>([]);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEscapeKey(open, onClose);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setResults([]);
    setSelected(0);
    inputRef.current?.focus();
    const cached = workspaceId ? readCachedWorkspaceSidebar(workspaceId) : null;
    if (cached) {
      setSpine(cached);
      return;
    }
    setSpine(null);
    if (workspaceId) {
      getCachedWorkspaceSidebar(workspaceId)
        .then(setSpine)
        .catch(() => {});
    }
  }, [open, workspaceId]);

  useEffect(() => {
    if (!open) {
      setResults([]);
      setSelected(0);
      return;
    }
    const fullPageSearch = fullPageSearchResult(searchScope, workspaceId, workspaceName, query);
    if (!query.trim()) {
      setResults([fullPageSearch]);
      setSelected(0);
      return;
    }
    const q = query.toLowerCase();

    // Local spine fuzzy match (instant)
    const local: Result[] = [fullPageSearch];
    if (spine && workspaceId) {
      const filesTree = spine.files;
      filesTree.pages.forEach((p) => {
        if (p.name.toLowerCase().includes(q))
          local.push({
            kind: "page",
            label: p.name.replace(/\.md$/, ""),
            href: `/workspaces/${workspaceId}/p/${p.id}`,
            detail: "Page",
          });
      });
      spine.sessions.forEach((s) => {
        if (s.session_id.toLowerCase().includes(q))
          local.push({
            kind: "session",
            label: `#${s.session_id}`,
            href: `/workspaces/${workspaceId}/sessions/${encodeURIComponent(s.session_id)}`,
            detail: s.agent_name,
          });
      });
      filesTree.folders.forEach((f) => {
        if (f.name.toLowerCase().includes(q))
          local.push({
            kind: "folder",
            label: f.name,
            href: `/workspaces/${workspaceId}/folders/${f.id}`,
            detail: `${f.page_count} pages · ${f.file_count} files`,
          });
      });
      filesTree.files.forEach((f) => {
        if (f.name.toLowerCase().includes(q))
          local.push({
            kind: "file",
            label: f.name,
            href: f.linked_table_id
              ? `/tables/${f.linked_table_id}?workspaceId=${workspaceId}`
              : `/workspaces/${workspaceId}/f/${f.id}`,
            detail: f.content_type,
          });
      });
    }
    setResults(local.slice(0, 12));
    setSelected(0);

    // Remote debounce (250ms): semantic page search
    if (!workspaceId) return;
    const timer = setTimeout(async () => {
      try {
        const pages = await semanticSearchPages(workspaceId, query, 6);
        const remote: Result[] = pages.map((p) => ({
          kind: "page" as const,
          label: p.name.replace(/\.md$/, ""),
          href: `/workspaces/${workspaceId}/p/${p.id}`,
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
  }, [query, open, spine, workspaceId, workspaceName, searchScope]);

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
    skill: "⚙︎",
    file: "📁",
  };

  return (
    <div className="fixed inset-0 z-[60] bg-transparent px-2 pt-2 sm:px-4" onClick={onClose}>
      <div
        className="mx-auto flex max-h-[calc(100vh-1rem)] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-border bg-base shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Search"
      >
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <svg className="h-4 w-4 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search Stash or jump to a page, session, or file..."
            className="min-w-0 flex-1 bg-transparent text-[14px] text-foreground placeholder:text-muted focus:outline-none"
            autoFocus
          />
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface hover:text-foreground"
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
                <span className="w-5 text-center text-[14px] text-muted">
                  {kindIcon[r.kind] || "·"}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{r.label}</div>
                  {r.detail && <div className="truncate text-[11px] text-muted">{r.detail}</div>}
                </div>
                <span className="rounded bg-surface px-1 py-0 text-[9px] uppercase tracking-wide text-muted ring-1 ring-border">
                  {r.kind}
                </span>
              </Link>
            ))}
          </div>
        ) : query ? (
          <div className="px-4 py-6 text-center text-[13px] text-muted">
            No results for &quot;{query}&quot;
          </div>
        ) : (
          <div className="px-4 py-6 text-center text-[13px] text-muted">
            Start typing to search this stash...
          </div>
        )}
      </div>
    </div>
  );
}

function fullPageSearchResult(
  scope: SearchScope | null,
  workspaceId: string | null,
  workspaceName: string | null | undefined,
  query: string
): Result {
  const params = new URLSearchParams(scope?.params);
  if (!scope && workspaceId) params.set("workspace", workspaceId);

  const q = query.trim();
  if (q) params.set("q", q);

  const label = scope?.label ?? workspaceName ?? (workspaceId ? "this workspace" : "Stash");
  const hrefParams = params.toString();

  return {
    kind: "search",
    label: q ? `Search ${label} for "${q}"` : `Search ${label}`,
    href: hrefParams ? `/search?${hrefParams}` : "/search",
    detail: scope?.detail ?? (workspaceId ? "Search this workspace" : "Search all workspaces"),
  };
}
