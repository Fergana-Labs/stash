"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

type Page = { id: string; name: string; content_type: string };
type FileRow = { id: string; name: string };
type Overview = {
  files: {
    pages: Page[];
    files: FileRow[];
  };
};

export default function SharingBrowseStep({ workspaceId }: StepCtx) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    apiFetch<Overview>(`/api/v1/workspaces/${workspaceId}/overview`)
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [workspaceId]);

  const pages = overview?.files.pages ?? [];
  const files = overview?.files.files ?? [];
  const total = pages.length + files.length;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          {total > 0 ? "Here's what you just added" : "Nothing here yet"}
        </h1>
        <p className="text-sm text-dim max-w-md">
          {total > 0
            ? "Click any item to view it. Anyone with the link can see it."
            : "Go back and drop a file, or have your agent publish one — then come back."}
        </p>
      </div>

      {error && (
        <div className="text-[12px] text-error rounded-lg border border-error/30 bg-error/10 px-3 py-2">
          {error}
        </div>
      )}

      {total > 0 && (
        <div className="rounded-2xl border border-border bg-surface divide-y divide-border-subtle">
          {pages.map((p) => (
            <Link
              key={`page-${p.id}`}
              href={`/pages/${p.id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-raised"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-[14px]" aria-hidden>
                  {p.content_type === "html" ? "🌐" : "📄"}
                </span>
                <span className="text-[13px] text-foreground truncate">
                  {p.name}
                </span>
              </div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
                {p.content_type}
              </span>
            </Link>
          ))}
          {files.map((f) => (
            <Link
              key={`file-${f.id}`}
              href={`/files/${f.id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-raised"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-[14px]" aria-hidden>
                  📎
                </span>
                <span className="text-[13px] text-foreground truncate">
                  {f.name}
                </span>
              </div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
                file
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
