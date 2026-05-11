"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  getStashSpine,
  semanticSearchPages,
  type StashSpine,
} from "../lib/api";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  stashId: string | null;
}

interface Result {
  kind: "page" | "session" | "skill" | "file" | "history";
  label: string;
  href: string;
  detail?: string;
}

export default function CommandPalette({ open, onClose, stashId }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [spine, setSpine] = useState<StashSpine | null>(null);
  const [results, setResults] = useState<Result[]>([]);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setResults([]);
    setSelected(0);
    inputRef.current?.focus();
    if (stashId && !spine) {
      getStashSpine(stashId)
        .then(setSpine)
        .catch(() => {});
    }
  }, [open, stashId, spine]);

  useEffect(() => {
    if (!open || !query.trim()) {
      setResults([]);
      return;
    }
    const q = query.toLowerCase();

    // Local spine fuzzy match (instant)
    const local: Result[] = [];
    if (spine && stashId) {
      spine.root_pages?.forEach((p) => {
        if (p.name.toLowerCase().includes(q))
          local.push({
            kind: "page",
            label: p.name.replace(/\.md$/, ""),
            href: `/stashes/${stashId}/p/${p.id}`,
            detail: "Page",
          });
      });
      spine.sessions.forEach((s) => {
        if (s.session_id.toLowerCase().includes(q))
          local.push({
            kind: "session",
            label: `#${s.session_id}`,
            href: `/stashes/${stashId}/sessions/${encodeURIComponent(s.session_id)}`,
            detail: s.agent_name,
          });
      });
      spine.skills.forEach((s) => {
        if (s.name.toLowerCase().includes(q))
          local.push({
            kind: "skill",
            label: `/${s.name}`,
            href: `/stashes/${stashId}/skills/${encodeURIComponent(s.name)}`,
            detail: s.description,
          });
      });
      spine.drive.files.forEach((f) => {
        if (f.name.toLowerCase().includes(q))
          local.push({
            kind: "file",
            label: f.name,
            href: f.linked_table_id
              ? `/tables/${f.linked_table_id}?workspaceId=${stashId}`
              : `/stashes/${stashId}/f/${f.id}`,
            detail: f.content_type,
          });
      });
    }
    setResults(local.slice(0, 12));
    setSelected(0);

    // Remote debounce (250ms): semantic page search
    if (!stashId) return;
    const timer = setTimeout(async () => {
      try {
        const pages = await semanticSearchPages(stashId, query, 6);
        const remote: Result[] = pages.map((p) => ({
          kind: "page" as const,
          label: p.name.replace(/\.md$/, ""),
          href: `/stashes/${stashId}/p/${p.id}`,
          detail: "Wiki page",
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
  }, [query, open, spine, stashId]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(s + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(s - 1, 0));
      } else if (e.key === "Enter" && results[selected]) {
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, results, selected, onClose]);

  if (!open) return null;

  const kindIcon: Record<string, string> = {
    page: "📄",
    session: "#",
    skill: "⚙︎",
    file: "📁",
    history: "⏱",
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/30 px-4 pt-[15vh]" onClick={onClose}>
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-base shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <svg className="h-4 w-4 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to a page, session, skill, or file…"
            className="flex-1 bg-transparent text-[14px] text-foreground placeholder:text-muted focus:outline-none"
            autoFocus
          />
          <span className="rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-muted ring-1 ring-border">esc</span>
        </div>

        {results.length > 0 ? (
          <div className="max-h-80 overflow-y-auto p-2">
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
            Start typing to search this stash…
          </div>
        )}
      </div>
    </div>
  );
}
