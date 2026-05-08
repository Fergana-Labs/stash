"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import {
  getStashSpine,
  getWorkspace,
  getWorkspaceMembers,
  joinWorkspace,
  type StashSpine,
} from "../../../lib/api";
import type { Workspace, WorkspaceMember } from "../../../lib/types";

interface CardItem {
  href: string;
  external?: boolean;
  icon: string;
  iconColor?: string;
  title: string;
  subtitle: string;
}

function CardGrid({ items, hover }: { items: CardItem[]; hover: "brand" | "indigo" }) {
  const hoverCls =
    hover === "indigo"
      ? "hover:border-indigo-300 hover:bg-indigo-50/30"
      : "hover:border-[var(--color-brand-200)] hover:bg-[var(--color-brand-50)]";
  return (
    <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
      {items.map((c) => {
        const cls =
          "flex items-center gap-3 rounded-lg border border-border bg-base p-3 text-left transition-colors " +
          hoverCls;
        const inner = (
          <>
            <span className={"text-2xl " + (c.iconColor || "")}>{c.icon}</span>
            <div className="min-w-0">
              <div className="truncate text-[13.5px] font-semibold text-foreground">{c.title}</div>
              <div className="truncate text-[11.5px] text-muted">{c.subtitle}</div>
            </div>
          </>
        );
        return c.external ? (
          <a
            key={c.href + c.title}
            href={c.href}
            target="_blank"
            rel="noopener noreferrer"
            className={cls}
          >
            {inner}
          </a>
        ) : (
          <Link key={c.href + c.title} href={c.href} className={cls}>
            {inner}
          </Link>
        );
      })}
    </div>
  );
}

export default function StashHomePage() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const { user, loading, logout } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [spine, setSpine] = useState<StashSpine | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setStash(await getWorkspace(stashId));
    } catch {
      setError("Stash not found");
    }
    try {
      setMembers(await getWorkspaceMembers(stashId));
    } catch {
      /* not a member yet */
    }
    try {
      setSpine(await getStashSpine(stashId));
    } catch {
      /* private */
    }
  }, [stashId]);

  useEffect(() => {
    if (!user) return;
    load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const isMember = !!user && members.some((m) => m.user_id === user.id);

  async function handleJoin() {
    if (!stash) return;
    try {
      await joinWorkspace(stash.invite_code);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to join");
    }
  }

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const sessions: CardItem[] = (spine?.sessions ?? []).slice(0, 6).map((s) => ({
    href: `/stashes/${stashId}/sessions/${encodeURIComponent(s.session_id)}`,
    icon: "#",
    title: `#${s.session_id.length > 28 ? s.session_id.slice(0, 28) + "…" : s.session_id}`,
    subtitle: `${s.agent_name} · ${formatBytes(s.size_bytes)}`,
  }));
  const skills: CardItem[] = (spine?.skills ?? []).map((s) => ({
    href: `/stashes/${stashId}/skills/${encodeURIComponent(s.name)}`,
    icon: "⚙︎",
    iconColor: "text-indigo-600",
    title: `/${s.name}`,
    subtitle: s.description || `${s.file_count} file${s.file_count === 1 ? "" : "s"}`,
  }));
  const driveFolders: CardItem[] = (spine?.drive.folders ?? []).slice(0, 3).map((f) => ({
    href: `/files?ws=${stashId}`,
    icon: "📁",
    title: f.name,
    subtitle: "Folder",
  }));
  const driveFiles: CardItem[] = (spine?.drive.files ?? []).slice(0, 8).map((f) => ({
    href: `/stashes/${stashId}/f/${f.id}`,
    icon: f.content_type?.includes("csv") ? "▦" : "📄",
    iconColor: f.content_type?.includes("csv")
      ? "text-emerald-600"
      : f.content_type?.includes("pdf")
      ? "text-rose-500"
      : f.content_type?.includes("html")
      ? "text-amber-600"
      : undefined,
    title: f.name,
    subtitle: `${f.content_type || "file"} · ${formatBytes(f.size_bytes)}`,
  }));

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="h-24 bg-gradient-to-r from-[var(--color-brand-200)] via-[var(--color-brand-100)] to-amber-100" />
        <div className="mx-auto -mt-6 max-w-3xl px-12 pb-16">
          <h1 className="font-display text-[34px] font-bold tracking-tight text-foreground">
            {stash?.name || "Loading…"}
          </h1>
          {stash?.description && (
            <p className="mt-2 text-[14.5px] leading-relaxed text-muted">{stash.description}</p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="rounded bg-surface px-2 py-0.5 text-muted">
              {members.length} member{members.length !== 1 ? "s" : ""}
            </span>
            <span className="rounded bg-surface px-2 py-0.5 text-muted">
              {stash?.is_public ? "Public" : "Private"}
            </span>
            {(stash?.tags ?? []).map((t) => (
              <span key={t} className="rounded bg-surface px-2 py-0.5 text-muted">
                {t}
              </span>
            ))}
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          {!isMember && stash && (
            <div className="mt-4 flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 text-[13px]">
              <span className="text-muted">You aren&apos;t a member of this stash.</span>
              <button
                onClick={handleJoin}
                className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              >
                Join stash
              </button>
            </div>
          )}

          {/* Start here narrative CTA */}
          {spine?.narrative && (
            <div className="mt-6 rounded-lg border border-[var(--color-brand-200)] bg-[var(--color-brand-50)]/60 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-brand-700)]">
                📌 Start here
              </div>
              <Link
                href={`/stashes/${stashId}/p/${spine.narrative.id}`}
                className="mt-1 block text-left"
              >
                <div className="text-[15px] font-semibold text-foreground">
                  Read the narrative →
                </div>
                <div className="text-[12.5px] text-muted">
                  3-min read · the why behind this stash
                </div>
              </Link>
            </div>
          )}

          {/* Stash structure callout */}
          <div className="mt-8 rounded-xl border border-border bg-surface/50 p-4">
            <div className="text-[10.5px] font-semibold uppercase tracking-wider text-muted">
              Stash structure
            </div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
              Every stash has three default folders mapped to how memory works for an agent:{" "}
              <span className="font-medium text-foreground">Sessions</span> (episodic — agent
              transcripts),{" "}
              <span className="font-medium text-foreground">Skills</span> (procedural — what the
              agent can do), and{" "}
              <span className="font-medium text-foreground">Drive</span> (semantic — files we
              create and manipulate).
            </p>
          </div>

          {/* Sessions */}
          <SectionHeader
            icon="💬"
            title="Sessions"
            subtitle="episodic"
            trailing={`${spine?.sessions.length ?? 0} transcript${
              spine?.sessions.length === 1 ? "" : "s"
            }`}
          />
          {sessions.length > 0 ? (
            <CardGrid items={sessions} hover="brand" />
          ) : (
            <EmptyState text="No sessions yet. Push agent transcripts via the CLI." />
          )}

          {/* Skills */}
          <SectionHeader
            icon="⚡"
            title="Skills"
            subtitle="procedural"
            trailing={`${spine?.skills.length ?? 0} skill${
              spine?.skills.length === 1 ? "" : "s"
            } · MCP exposed`}
          />
          {skills.length > 0 ? (
            <CardGrid items={skills} hover="indigo" />
          ) : (
            <EmptyState
              text="No skills yet."
              action={{ href: "#", label: "Drop a SKILL.md folder via `stash skill add`" }}
            />
          )}

          {/* Drive */}
          <SectionHeader
            icon="📁"
            title="Drive"
            subtitle="semantic"
            trailing={`${(spine?.drive.files.length ?? 0)} file${
              spine?.drive.files.length === 1 ? "" : "s"
            } · ${(spine?.drive.folders.length ?? 0)} folder${
              spine?.drive.folders.length === 1 ? "" : "s"
            }`}
          />
          {driveFolders.length + driveFiles.length > 0 ? (
            <CardGrid items={[...driveFolders, ...driveFiles]} hover="brand" />
          ) : (
            <EmptyState text="Upload PDFs, sheets, or create wiki pages." />
          )}
        </div>
      </div>
    </AppShell>
  );
}

function SectionHeader({
  icon,
  title,
  subtitle,
  trailing,
}: {
  icon: string;
  title: string;
  subtitle: string;
  trailing: string;
}) {
  return (
    <div className="mt-8 flex items-baseline justify-between">
      <h2 className="font-display text-xl font-semibold text-foreground">
        {icon} {title}{" "}
        <span className="text-[12px] font-normal italic text-muted">· {subtitle}</span>
      </h2>
      <span className="text-[11.5px] text-muted">{trailing}</span>
    </div>
  );
}

function EmptyState({
  text,
  action,
}: {
  text: string;
  action?: { href: string; label: string };
}) {
  return (
    <div className="mt-2 rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
      {text}
      {action && (
        <div className="mt-2">
          <span className="font-mono text-[12px]">{action.label}</span>
        </div>
      )}
    </div>
  );
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}
