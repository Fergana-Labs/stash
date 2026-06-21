"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { BasicPageSkeleton } from "@/components/SkeletonStates";
import { getPublicSessionFolder, type PublicSessionFolder } from "@/lib/api";

// Read-only viewer for a session folder reached by slug. Renders for anyone the
// access rules allow (a public folder needs no login); the layout exempts
// /session-folders/ from the signed-in redirect.
export default function PublicSessionFolderPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const [data, setData] = useState<PublicSessionFolder | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    getPublicSessionFolder(slug)
      .then(setData)
      .catch(() => setNotFound(true));
  }, [slug]);

  if (notFound) {
    return (
      <div className="mx-auto max-w-[760px] px-6 py-20 text-center">
        <h1 className="font-display text-[22px] font-bold text-foreground">Folder not found</h1>
        <p className="mt-2 text-[13.5px] text-muted">
          This folder is private or the link is wrong.
        </p>
      </div>
    );
  }

  if (!data) return <BasicPageSkeleton />;

  const { folder, sessions } = data;

  return (
    <div className="mx-auto max-w-[820px] px-6 py-10">
      <div className="flex items-center gap-2 text-[12px] text-muted">
        <span aria-hidden>{folder.is_default ? "🗃️" : "📁"}</span>
        <span>Shared session folder</span>
      </div>
      <h1 className="mt-2 font-display text-[24px] font-bold tracking-tight text-foreground">
        {folder.name}
      </h1>
      <p className="mt-1 text-[12.5px] text-muted">
        {sessions.length} session{sessions.length === 1 ? "" : "s"}
        {folder.owner_display_name ? ` · by ${folder.owner_display_name}` : ""}
      </p>

      {sessions.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted">
          No sessions in this folder yet.
        </div>
      ) : (
        <div className="mt-6 overflow-hidden rounded-xl border border-border bg-surface">
          {sessions.map((s) => (
            <Link
              key={s.id}
              href={`/sessions/${encodeURIComponent(s.session_id)}`}
              className="group flex items-center gap-3 border-b border-border-subtle px-4 py-3 last:border-b-0 hover:bg-[var(--color-brand-50)]"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13.5px] font-medium text-foreground group-hover:text-[var(--color-brand-700)]">
                  {s.session_id}
                </span>
                <span className="mt-0.5 block truncate text-[11.5px] text-muted">
                  {s.user_name ? `${s.user_name} · ` : ""}
                  {s.agent_name || "agent"} · {s.event_count} event{s.event_count === 1 ? "" : "s"}
                </span>
              </span>
              <span className="shrink-0 text-[11.5px] text-muted">{relativeTime(s.last_event_at)}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}
