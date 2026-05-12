"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "../../../components/AppShell";
import MembersModal from "../../../components/MembersModal";
import { useAuth } from "../../../hooks/useAuth";
import {
  createFolder,
  createPage,
  getStashSpine,
  getWorkspace,
  getWorkspaceMembers,
  joinWorkspace,
  uploadFile,
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
  const [membersOpen, setMembersOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
      setSpine(
        await getStashSpine(stashId, {
          sessionLimit: 20,
          wikiDepth: "full",
          includeFileUrls: false,
        })
      );
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

  // Root-level wiki contents only. Nested folders/pages/files surface
  // through their parent folder's detail page, not here.
  const rootFolders = (spine?.wiki.folders ?? []).filter((f) => !f.parent_folder_id);
  const rootPages = (spine?.wiki.pages ?? []).filter((p) => !p.folder_id);
  const rootFiles = (spine?.wiki.files ?? []).filter((f) => !f.folder_id);

  const wikiFolderItems: CardItem[] = rootFolders.map((f) => ({
    href: `/stashes/${stashId}/folders/${f.id}`,
    icon: "📁",
    title: f.name,
    subtitle: [
      f.page_count ? `${f.page_count} page${f.page_count === 1 ? "" : "s"}` : null,
      f.file_count ? `${f.file_count} file${f.file_count === 1 ? "" : "s"}` : null,
      f.has_skill ? "SKILL.md" : null,
    ]
      .filter(Boolean)
      .join(" · ") || "Empty folder",
  }));
  const wikiPageItems: CardItem[] = rootPages.map((p) => ({
    href: `/stashes/${stashId}/p/${p.id}`,
    icon: "📄",
    title: p.name.replace(/\.md$/, ""),
    subtitle: "Page",
  }));
  const wikiFileItems: CardItem[] = rootFiles.slice(0, 12).map((f) => {
    const isCsvLinked = f.content_type?.includes("csv") && f.linked_table_id;
    return {
      href: isCsvLinked
        ? `/tables/${f.linked_table_id}?workspaceId=${stashId}`
        : `/stashes/${stashId}/f/${f.id}`,
      icon: f.content_type?.includes("csv") ? "▦" : "📄",
      iconColor: f.content_type?.includes("csv")
        ? "text-emerald-600"
        : f.content_type?.includes("pdf")
        ? "text-rose-500"
        : f.content_type?.includes("html")
        ? "text-amber-600"
        : undefined,
      title: f.name,
      subtitle: isCsvLinked
        ? `table · ${formatBytes(f.size_bytes)}`
        : `${f.content_type || "file"} · ${formatBytes(f.size_bytes)}`,
    };
  });
  const wikiItems = [...wikiFolderItems, ...wikiPageItems, ...wikiFileItems];
  const totalFolders = spine?.wiki.folders.length ?? 0;
  const totalPages = spine?.wiki.pages.length ?? 0;
  const totalFiles = spine?.wiki.files.length ?? 0;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="h-32 bg-gradient-to-r from-[var(--color-brand-200)] via-amber-100 to-rose-100" />
        <div className="mx-auto -mt-8 max-w-3xl px-12 pb-16">
          <div className="mb-2 text-5xl leading-none">📊</div>
          <h1 className="font-display text-[34px] font-bold tracking-tight text-foreground">
            {stash?.name || "Loading…"}
          </h1>
          {stash?.description && (
            <p className="mt-2 text-[14.5px] leading-relaxed text-muted">{stash.description}</p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <button onClick={() => setMembersOpen(true)} title="Manage members">
              <MemberStack members={members} />
            </button>
            <span>· updated {stash?.updated_at ? formatRelative(stash.updated_at) : ""}</span>
            <span className="text-muted">·</span>
            <span>{stash?.is_public ? "Public" : "Private"}</span>
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

          {/* Stash structure callout */}
          <div className="mt-8 rounded-xl border border-border bg-surface/50 p-4">
            <div className="text-[10.5px] font-semibold uppercase tracking-wider text-muted">
              Stash structure
            </div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
              Two surfaces:{" "}
              <span className="font-medium text-foreground">Sessions</span> (agent transcripts —
              episodic memory) and{" "}
              <span className="font-medium text-foreground">Wiki</span> (pages, files, and
              folders — the structured, shared content of the stash).
            </p>
          </div>

          {/* Sessions */}
          <SectionHeader
            icon="💬"
            title="Sessions"
            subtitle="episodic"
            trailing={`${spine?.session_count ?? spine?.sessions.length ?? 0} transcript${
              (spine?.session_count ?? spine?.sessions.length ?? 0) === 1 ? "" : "s"
            }`}
          />
          {sessions.length > 0 ? (
            <CardGrid items={sessions} hover="brand" />
          ) : (
            <EmptyState text="No sessions yet. Push agent transcripts via the CLI." />
          )}

          {/* Wiki */}
          <SectionHeader
            icon="📖"
            title="Wiki"
            subtitle="structured"
            trailing={`${totalFolders} folder${totalFolders === 1 ? "" : "s"} · ${
              totalPages
            } page${totalPages === 1 ? "" : "s"} · ${totalFiles} file${
              totalFiles === 1 ? "" : "s"
            }`}
          />
          {isMember && (
            <div className="mt-2 mb-3 flex flex-wrap items-center gap-2">
              <input ref={fileInputRef} type="file" className="hidden" onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                try {
                  await uploadFile(stashId, file);
                  await load();
                } catch { /* */ }
                if (fileInputRef.current) fileInputRef.current.value = "";
              }} />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + Upload file
              </button>
              <button
                onClick={async () => {
                  try {
                    const p = await createPage(stashId, "Untitled");
                    router.push(`/stashes/${stashId}/p/${p.id}`);
                  } catch { /* */ }
                }}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + New page
              </button>
              <button
                onClick={async () => {
                  const name = window.prompt("Folder name?");
                  if (!name?.trim()) return;
                  try {
                    await createFolder(stashId, name.trim());
                    await load();
                  } catch { /* */ }
                }}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + New folder
              </button>
            </div>
          )}
          {wikiItems.length > 0 ? (
            <CardGrid items={wikiItems} hover="brand" />
          ) : (
            <EmptyState text="Upload PDFs, sheets, or create wiki pages." />
          )}
        </div>
      </div>
      <MembersModal stashId={stashId} open={membersOpen} onClose={() => setMembersOpen(false)} />
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

const AVATAR_PALETTE: { bg: string; fg: string }[] = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

function avatarFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function MemberStack({ members }: { members: WorkspaceMember[] }) {
  if (!members.length) return null;
  const display = members.slice(0, 5);
  const overflow = members.length - display.length;
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex -space-x-1.5">
        {display.map((m) => {
          const label = (m.display_name || m.name || "?").trim();
          const palette = avatarFor(label);
          return (
            <span
              key={m.user_id}
              className={
                "inline-flex h-5 w-5 items-center justify-center rounded-full border-2 border-base text-[9.5px] font-semibold " +
                palette.bg +
                " " +
                palette.fg
              }
              title={`${label}${m.role && m.role !== "member" ? ` · ${m.role}` : ""}`}
            >
              {label.slice(0, 2).toUpperCase()}
            </span>
          );
        })}
      </div>
      {overflow > 0 && <span className="text-[11px] text-muted">+{overflow}</span>}
      <span className="text-[12px] text-muted">
        {members.length} member{members.length !== 1 ? "s" : ""}
      </span>
    </div>
  );
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}
